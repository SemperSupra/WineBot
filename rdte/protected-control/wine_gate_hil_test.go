//go:build linux

package main

import (
 "context"
 "fmt"
 "os"
 "os/exec"
 "path/filepath"
 "strconv"
 "strings"
 "testing"
 "time"
)

// Real Wine workload bridge on disposable hosted Linux ONLY. Docker is an
// external effect authority; a successful start acknowledgement is not a
// distributed fencing proof. Never release or retry this generation.
func TestWine11GateStopHIL(t *testing.T){
 if os.Getenv("WINEBOT_REAL_WINE_GATE")!="1"{t.Skip("dedicated disposable public HIL only")}
 if os.Geteuid()!=0{t.Fatal("fixture requires root")}
 ctx,cancel:=context.WithTimeout(context.Background(),8*time.Minute)
 defer cancel()
 call:=func(args ...string)(string,error){
  b,err:=exec.CommandContext(ctx,args[0],args[1:]...).Output()
  return strings.TrimSpace(string(b)),err
 }
 must:=func(stage string,args ...string)string{
  t.Helper()
  out,err:=call(args...)
  if err!=nil{t.Fatalf("WINE_GATE_HIL stage=%s failed",stage)}
  return out
 }
 root:=lifecycleTestRoot(t)
 if err:=lifecycleProvision(root,0);err!=nil{t.Fatal("journal provisioning failed")}
 name:="winebotr046"+strconv.Itoa(os.Getpid())
 driver:=must("engine_driver","docker","info","--format","{{.CgroupDriver}}")
 var scope,parent string
 switch driver{
 case "systemd":
  parent=name+".slice"
  unit:=filepath.Join("/run/systemd/system",parent)
  if err:=os.WriteFile(unit,[]byte("[Unit]\nDescription=Disposable WineBot RDTE scope\n[Slice]\n"),0600);err!=nil{t.Fatal("scope unit creation failed")}
  defer func(){
   _=exec.Command("systemctl","stop",parent).Run()
   _=os.Remove(unit)
   _=exec.Command("systemctl","daemon-reload").Run()
  }()
  must("reload","systemctl","daemon-reload")
  must("scope_start","systemctl","start",parent)
  cg:=must("scope_path","systemctl","show","-p","ControlGroup","--value",parent)
  if cg!="/"+parent{t.Fatal("unexpected disposable slice identity")}
  scope=filepath.Join("/sys/fs/cgroup",cg)
 case "cgroupfs":
  scope=filepath.Join("/sys/fs/cgroup",name)
  if err:=os.Mkdir(scope,0700);err!=nil{t.Fatal("scope creation failed")}
  defer os.Remove(scope)
  parent="/"+name
 default:t.Fatal("unsupported engine cgroup driver")
 }
 dir,err:=os.Open(scope)
 if err!=nil{t.Fatal("scope open failed")}
 defer dir.Close()
 id,err:=cgroupID(dir)
 if err!=nil{t.Fatal("scope identity failed")}
 image:=must("image_identity","docker","image","inspect","winebot-r046:local","--format","{{.Id}}")
 if !strings.HasPrefix(image,"sha256:") || len(image)!=71{t.Fatal("invalid local image identity")}
 g,err:=newWriterGate(root,0,0,dir,id)
 if err!=nil{t.Fatal("scope reservation failed",err)}
 e,err:=newEmergencyDispatch(g)
 if err!=nil{t.Fatal(err)}
 script:=`set -eu
 export HOME=/home/winebot WINEPREFIX=/tmp/winebot-r046-prefix DISPLAY=:93
 export WINEDLLOVERRIDES=mscoree,mshtml=
 test "$(id -u)" = 1000
 test "$(dpkg-query -W -f='${Version}' winehq-stable)" = '11.0.0.0~trixie-1'
 wine --version | grep -Eq '^wine-11[.]0([[:space:]]|$)'
 echo WINE_GATE_HIL=VERSION_OK
 Xvfb "$DISPLAY" -screen 0 1024x768x24 -noreset >/dev/null 2>&1 &
 ready=0
 for i in $(seq 1 40); do
   if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then ready=1; break; fi
   sleep .25
 done
 test "$ready" = 1
 timeout -k 5s 120s wineboot -i >/dev/null 2>&1
 test -s "$WINEPREFIX/system.reg"
 echo WINE_GATE_HIL=PREFIX_OK
 wine notepad >/dev/null 2>&1 &
 app=$!
 ready=0
 for i in $(seq 1 80); do
   if xdotool search --onlyvisible --class notepad >/dev/null 2>&1; then ready=1; break; fi
   sleep .5
 done
 test "$ready" = 1
 echo WINE_GATE_HIL=WINDOW_OK
 wait "$app"
 `
 container:=must("create_fixture","docker","create","--name",name,"--cgroup-parent",parent,
  "--network","none","--user","1000:1000","--cap-drop","ALL","--security-opt","no-new-privileges",
  "--pids-limit","256","--memory","2g","--init","--entrypoint","/bin/sh",image,"-c",script)
 if len(container)!=64{t.Fatal("invalid container identity")}
 defer exec.Command("docker","rm","-f",container).Run()
 if err=e.run(func(context.Context)error{
  _,err:=call("docker","start",container)
  return err
 });err!=nil{t.Fatal("start effect unknown; no retry")}
 pid:=must("container_pid","docker","inspect","--format","{{.State.Pid}}",container)
 pidn,err:=strconv.Atoi(pid)
 if err!=nil || pidn<=0{t.Fatal("invalid fixture process")}
 membership,err:=os.ReadFile(fmt.Sprintf("/proc/%d/cgroup",pidn))
 if err!=nil{t.Fatal("membership unavailable")}
 rel:=strings.TrimPrefix(scope,"/sys/fs/cgroup")
 matched:=false
 for _,line:=range strings.Split(string(membership),"\n"){
  if line=="0::"+rel || strings.HasPrefix(line,"0::"+rel+"/"){matched=true}
 }
 if !matched{t.Fatal("engine process outside admitted scope")}
 deadline:=time.Now().Add(220*time.Second)
 for {
  out,err:=call("docker","logs","--tail","20",container)
  if err==nil && strings.Contains(out,"WINE_GATE_HIL=VERSION_OK") &&
   strings.Contains(out,"WINE_GATE_HIL=PREFIX_OK") && strings.Contains(out,"WINE_GATE_HIL=WINDOW_OK"){break}
  if time.Now().After(deadline){t.Fatal("Wine11 prefix/window qualification failed")}
  if must("running","docker","inspect","--format","{{.State.Running}}",container)!="true"{t.Fatal("fixture exited before readiness")}
  time.Sleep(time.Second)
 }
 if p,err:=cgroupPopulated(dir,id);err!=nil || !p{t.Fatal("live Wine scope not observed")}
 t.Log("WINE_GATE_HIL stage=wine11_window_ready_in_admitted_scope")
 if _,err=e.requestPersistentStop();err!=nil{t.Fatal("durable STOP failed",err)}
 must("stop_fixture","docker","stop","--time","5",container)
 if must("stopped","docker","inspect","--format","{{.State.Running}}",container)!="false"{t.Fatal("engine termination unconfirmed")}
 deadline=time.Now().Add(10*time.Second)
 for{
  p,err:=cgroupPopulated(dir,id)
  if err!=nil{t.Fatal("scope observation unavailable")}
  if !p{break}
  if time.Now().After(deadline){t.Fatal("scope still populated")}
  time.Sleep(100*time.Millisecond)
 }
 if err=g.stopAndReconcile();err==nil{t.Fatal("STOP allowed automatic release")}
 if _,err=reserveWriterGate(root,0,g.generation,func()(bool,error){return false,nil});err==nil{t.Fatal("replacement writer admitted")}
 s,err:=lifecycleRead(root,0)
 if err!=nil || s.Phase!="QUARANTINED"{t.Fatal("quarantine missing")}
 t.Log("WINE_GATE_HIL stage=terminated_empty_but_quarantined")
}
