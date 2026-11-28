//go:build windows

// A deliberately tiny Windows-API installation fixture. It is original source
// for RDTE, NOT an arbitrary third-party installer or production application.
// The opt-in guard prevents inadvertent execution outside isolated CI.
package main

import (
 "errors"
 "fmt"
 "os"
 "path/filepath"
 "syscall"
 "unsafe"
)

const (
 fixtureKey = `Software\WineBotInstallerFixture`
 fixtureDir = "WineBotInstallerFixture"
 fixtureValue = "InstallState"
 fixtureVersion = "synthetic-v1"
 hkeyCurrentUser = uintptr(0x80000001)
 keySetValue = uintptr(0x0002)
 regSZ = uintptr(1)
)

var (
 advapi32 = syscall.NewLazyDLL("advapi32.dll")
 regCreateKeyExW = advapi32.NewProc("RegCreateKeyExW")
 regSetValueExW = advapi32.NewProc("RegSetValueExW")
 regCloseKey = advapi32.NewProc("RegCloseKey")
 regDeleteKeyW = advapi32.NewProc("RegDeleteKeyW")
)

func pathForFixture() (string,error) {
 base:=os.Getenv("APPDATA")
 if base=="" {return "",errors.New("missing APPDATA")}
 // Only a fixed subdirectory, never user-supplied paths.
 return filepath.Join(base,fixtureDir),nil
}
func writeKey() error {
 keyName,err:=syscall.UTF16PtrFromString(fixtureKey)
 if err!=nil {return errors.New("bad key")}
 var key uintptr
 status,_,_:=regCreateKeyExW.Call(hkeyCurrentUser,uintptr(unsafe.Pointer(keyName)),0,0,0,keySetValue,0,uintptr(unsafe.Pointer(&key)),0)
 if status!=0 {return errors.New("registry key create failed")}
 defer regCloseKey.Call(key)
 valueName,err:=syscall.UTF16PtrFromString(fixtureValue)
 if err!=nil {return errors.New("bad value name")}
 data,err:=syscall.UTF16FromString(fixtureVersion)
 if err!=nil {return errors.New("bad value contents")}
 status,_,_=regSetValueExW.Call(key,uintptr(unsafe.Pointer(valueName)),0,regSZ,uintptr(unsafe.Pointer(&data[0])),uintptr(len(data)*2))
 if status!=0 {return errors.New("registry value write failed")}
 return nil
}
func removeKey() error {
 name,err:=syscall.UTF16PtrFromString(fixtureKey)
 if err!=nil {return errors.New("bad key")}
 code,_,_:=regDeleteKeyW.Call(hkeyCurrentUser,uintptr(unsafe.Pointer(name)))
 if code!=0 {return errors.New("registry key delete failed")}
 return nil
}
func install() error {
 dir,err:=pathForFixture()
 if err!=nil {return err}
 if err:=os.Mkdir(dir,0700);err!=nil {return errors.New("fixture path already exists or not writable")}
 // An installation has both filesystem and registry postconditions.
 if err:=os.WriteFile(filepath.Join(dir,"installed.txt"),[]byte(fixtureVersion+"\n"),0600);err!=nil {return errors.New("fixture file failed")}
 return writeKey()
}
func uninstall() error {
 dir,err:=pathForFixture()
 if err!=nil {return err}
 proof:=filepath.Join(dir,"installed.txt")
 b,err:=os.ReadFile(proof)
 if err!=nil || string(b)!=fixtureVersion+"\n" {return errors.New("missing fixture identity; refusing cleanup")}
 entries,err:=os.ReadDir(dir)
 if err!=nil || len(entries)!=1 || entries[0].Name()!="installed.txt" {return errors.New("unexpected files; refusing cleanup")}
 if err:=removeKey();err!=nil{return err}
 if err:=os.Remove(proof);err!=nil{return errors.New("file delete failed")}
 if err:=os.Remove(dir);err!=nil{return errors.New("directory delete failed")}
 return nil
}
func main() {
 if os.Getenv("WINEBOT_FIXTURE_PERMIT")!="synthetic-ci" || len(os.Args)!=2 {
  fmt.Fprintln(os.Stderr,"WIN_INSTALL_FIXTURE stage=not_authorized")
  os.Exit(2)
 }
 var err error
 var stage string
 switch os.Args[1] {
 case "install":stage="installed";err=install()
 case "uninstall":stage="uninstalled";err=uninstall()
 default:stage="invalid";err=errors.New("invalid command")
 }
 if err!=nil {
  fmt.Fprintln(os.Stderr,"WIN_INSTALL_FIXTURE stage=failed")
  os.Exit(1)
 }
 fmt.Printf("WIN_INSTALL_FIXTURE stage=%s\n",stage)
}
