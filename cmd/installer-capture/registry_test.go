package main

import (
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func TestWineRegistrySemanticDeltaIgnoresTimeAndOrder(t *testing.T) {
 before := "WINE REGISTRY Version 2\n;; All keys relative to \\\\User\\\\SYNTHETIC\n#arch=win64\n\n[Software\\\\Test] 100\n\"Name\"=\"safe string\"\n\"Amount\"=dword:0000000A\n\"Binary\"=hex:00,01,02,\\\n  03,04\n"
 after := "WINE REGISTRY Version 2\n;; All keys relative to \\\\User\\\\SYNTHETIC\n#arch=win64\n\n[Software\\\\Test] 999\n\"Binary\"=hex:00,01,02,03,04\n\"Amount\"=dword:0000000a\n\"Name\"=\"safe string\"\n"
 a,err:=parseWineRegistry(strings.NewReader(before))
 if err!=nil {t.Fatal(err)}
 b,err:=parseWineRegistry(strings.NewReader(after))
 if err!=nil {t.Fatal(err)}
 d,err:=diffRegistry(a,b)
 if err!=nil {t.Fatal(err)}
 if len(d.Changes)!=0 {t.Fatalf("timestamp/order/hex continuation caused %d false changes",len(d.Changes))}
}

func TestWineRegistryDetectsChangedAddedAndRemoved(t *testing.T) {
 prefix:="WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n#arch=win64\n"
 a,err:=parseWineRegistry(strings.NewReader(prefix+"[Software\\\\Test] 123\n\"State\"=\"BEFORE_PRIVATE\"\n\"Removed\"=dword:00000002\n"))
 if err!=nil{t.Fatal(err)}
 b,err:=parseWineRegistry(strings.NewReader(prefix+"[Software\\\\Test] 456\n\"State\"=\"AFTER_PRIVATE\"\n\"Added\"=str(2):\"path with spaces\"\n"))
 if err!=nil{t.Fatal(err)}
 d,err:=diffRegistry(a,b)
 if err!=nil{t.Fatal(err)}
 got:=map[string]string{}
 for _,c:=range d.Changes {got[c.Name]=c.Operation}
 for k,want:=range map[string]string{"State":"changed","Removed":"removed","Added":"added"} {
  if got[k]!=want{t.Fatalf("%s operation %q want %q",k,got[k],want)}
 }
 raw,_:=json.Marshal(d)
 for _,secret:=range []string{"BEFORE_PRIVATE","AFTER_PRIVATE","path with spaces"} {
  if strings.Contains(string(raw),secret){t.Fatalf("registry contents leaked into digest output")}
 }
}

func TestWineRegistryRejectsBadOrAmbiguousInput(t *testing.T) {
 header:="WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n#arch=win64\n"
 tests:=[]string{
  "Windows Registry Editor Version 5.00\n",
  "WINE REGISTRY Version 2\n",
  header+"\"Value\"=\"outside key\"\n",
  header+"[Software\\\\Test]\n\"X\"=qword:0000000000000001\n",
  header+"[Software\\\\Test]\n\"X\"=dword:not-hex\n",
  header+"[Software\\\\Test]\n\"X\"=hex:0g,00\n",
  header+"[Software\\\\Test]\n\"X\"=hex:01,\\\n",
  header+"[Software\\\\Test]\n\"X\"=hex:aa\n\"X\"=hex:bb\n",
  header+"[Software\\\\Test]\n[Software\\\\Test]\n",
  header+"#arch=win32\n",
  header+"[Software\\\\Test]\n\"X\"=\"unterminated\n",
 }
 for i,s:=range tests {
  if _,err:=parseWineRegistry(strings.NewReader(s));err==nil {t.Fatalf("invalid registry case %d accepted",i)}
 }
}

func TestWineRegistryRootAndArchMismatchesFailClosed(t *testing.T) {
 base:="WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n#arch=win64\n[Software\\\\X]\n"
 a,err:=parseWineRegistry(strings.NewReader(base))
 if err!=nil{t.Fatal(err)}
 b,err:=parseWineRegistry(strings.NewReader(strings.Replace(base,"win64","win32",1)))
 if err!=nil{t.Fatal(err)}
 if _,err:=diffRegistry(a,b);err==nil{t.Fatal("different registry architecture silently accepted")}
 c,err:=parseWineRegistry(strings.NewReader(strings.Replace(base,"\\\\Machine","\\\\User",1)))
 if err!=nil{t.Fatal(err)}
 if _,err:=diffRegistry(a,c);err==nil{t.Fatal("different registry root silently accepted")}
}

func TestWineRegistryPrivateIOAndCLI(t *testing.T) {
 dir:=t.TempDir()
 before:=filepath.Join(dir,"before.reg")
 after:=filepath.Join(dir,"after.reg")
 out:=filepath.Join(dir,"delta.json")
 raw:="WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n#arch=win64\n[Software\\\\Fixture]\n\"Install\"=\"old\"\n"
 if err:=os.WriteFile(before,[]byte(raw),0600);err!=nil{t.Fatal(err)}
 if err:=os.WriteFile(after,[]byte(strings.Replace(raw,"\"old\"","\"new\"",1)),0600);err!=nil{t.Fatal(err)}
 if err:=run([]string{"regdiff","-before",before,"-after",after,"-out",out});err!=nil{t.Fatal(err)}
 data,err:=os.ReadFile(out)
 if err!=nil{t.Fatal(err)}
 var d RegistryDelta
 if err:=json.Unmarshal(data,&d);err!=nil{t.Fatal(err)}
 if len(d.Changes)!=1 || d.Changes[0].Operation!="changed"{t.Fatalf("unexpected delta %+v",d.Changes)}
 if strings.Contains(string(data),"\"old\"")||strings.Contains(string(data),"\"new\""){t.Fatal("raw registry value in output")}
 if err:=run([]string{"regdiff","-before",before,"-after",after,"-out",out});err==nil{t.Fatal("overwrote existing evidence")}
 link:=filepath.Join(dir,"linked.reg")
 if err:=os.Symlink(before,link);err!=nil{t.Skipf("symlink unavailable: %v",err)}
 if _,err:=readPrivateRegistry(link);err==nil{t.Fatal("followed untrusted registry symlink")}
}
