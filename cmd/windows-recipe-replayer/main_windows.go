//go:build windows

// Independent original WinAPI recipe replay. Synthetic fixture only.
// The real installer is not imported or executed by this process.
package main

import (
 "bytes"
 "crypto/sha256"
 "embed"
 "encoding/binary"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "os"
 "path/filepath"
 "strings"
 "syscall"
 "unicode/utf16"
 "unsafe"
)

//go:embed recipe.json
var recipeFS embed.FS

type Recipe struct {
 Schema int `json:"schema"`
 ID string `json:"id"`
 AppdataSubdir string `json:"appdata_subdir"`
 FileName string `json:"file_name"`
 FileContent string `json:"file_content"`
 RegistryKey string `json:"registry_key"`
 RegistryValueName string `json:"registry_value_name"`
 RegistryValueType string `json:"registry_value_type"`
 RegistryData string `json:"registry_data"`
}

var (
 advapi = syscall.NewLazyDLL("advapi32.dll")
 createKey = advapi.NewProc("RegCreateKeyExW")
 setValue = advapi.NewProc("RegSetValueExW")
 queryValue = advapi.NewProc("RegQueryValueExW")
 openKey = advapi.NewProc("RegOpenKeyExW")
 closeKey = advapi.NewProc("RegCloseKey")
 deleteKey = advapi.NewProc("RegDeleteKeyW")
)
const hkcu = uintptr(0x80000001)
const keySetValue = uintptr(0x0002)
const keyQueryValue = uintptr(0x0001)
const regSZ = uint32(1)

func loadRecipe() (Recipe,error) {
 var r Recipe
 raw,err:=recipeFS.ReadFile("recipe.json")
 if err!=nil {return r,errors.New("recipe missing")}
 d:=json.NewDecoder(bytes.NewReader(raw));d.DisallowUnknownFields()
 if err:=d.Decode(&r);err!=nil{return r,errors.New("recipe invalid")}
 if err:=d.Decode(new(any));err!=io.EOF{return r,errors.New("trailing recipe data")}
 // Fail closed on any different path, key or operation: this is not a
 // general-purpose recipe runner and cannot touch an arbitrary prefix.
 if r.Schema!=1 || r.ID!="winebot.synthetic.winapi.fixture" ||
  r.AppdataSubdir!="WineBotInstallerFixture" || r.FileName!="installed.txt" ||
  r.FileContent!="synthetic-v1\n" ||
  r.RegistryKey!=`Software\WineBotInstallerFixture` ||
  r.RegistryValueName!="InstallState" || r.RegistryValueType!="REG_SZ" ||
  r.RegistryData!="synthetic-v1" {return r,errors.New("recipe not allowlisted")}
 return r,nil
}
func fixturePath(r Recipe)(string,string,error){
 dir:=os.Getenv("APPDATA")
 if dir==""{return "","",errors.New("APPDATA unavailable")}
 out:=filepath.Join(dir,r.AppdataSubdir)
 return out,filepath.Join(out,r.FileName),nil
}
func utf16Pointer(s string)(*uint16,error){return syscall.UTF16PtrFromString(s)}
func regWrite(r Recipe)error{
 key,err:=utf16Pointer(r.RegistryKey);if err!=nil{return err}
 name,err:=utf16Pointer(r.RegistryValueName);if err!=nil{return err}
 val,err:=syscall.UTF16FromString(r.RegistryData);if err!=nil{return err}
 var handle uintptr
 result,_,_:=createKey.Call(hkcu,uintptr(unsafe.Pointer(key)),0,0,0,keySetValue,0,uintptr(unsafe.Pointer(&handle)),0)
 if result!=0{return errors.New("registry key create failed")}
 defer closeKey.Call(handle)
 result,_,_=setValue.Call(handle,uintptr(unsafe.Pointer(name)),0,uintptr(regSZ),uintptr(unsafe.Pointer(&val[0])),uintptr(len(val)*2))
 if result!=0{return errors.New("registry value write failed")}
 return nil
}
func regRead(r Recipe)(string,error){
 key,err:=utf16Pointer(r.RegistryKey);if err!=nil{return "",err}
 name,err:=utf16Pointer(r.RegistryValueName);if err!=nil{return "",err}
 var handle uintptr
 result,_,_:=openKey.Call(hkcu,uintptr(unsafe.Pointer(key)),0,keyQueryValue,uintptr(unsafe.Pointer(&handle)))
 if result!=0{return "",errors.New("registry key unavailable")}
 defer closeKey.Call(handle)
 var kind uint32; var length uint32
 result,_,_=queryValue.Call(handle,uintptr(unsafe.Pointer(name)),0,uintptr(unsafe.Pointer(&kind)),0,uintptr(unsafe.Pointer(&length)))
 if result!=0 || kind!=regSZ || length<2 || length>4096 || length%2!=0{return "",errors.New("registry type/length mismatch")}
 data:=make([]byte,length)
 result,_,_=queryValue.Call(handle,uintptr(unsafe.Pointer(name)),0,uintptr(unsafe.Pointer(&kind)),uintptr(unsafe.Pointer(&data[0])),uintptr(unsafe.Pointer(&length)))
 if result!=0 || kind!=regSZ || length%2!=0 || length>uint32(len(data)){return "",errors.New("registry query failed")}
 chars:=make([]uint16,length/2)
 for i:=range chars{chars[i]=binary.LittleEndian.Uint16(data[i*2:])}
 if len(chars)==0 || chars[len(chars)-1]!=0{return "",errors.New("unterminated registry string")}
 return string(utf16.Decode(chars[:len(chars)-1])),nil
}
func verify(r Recipe)error{
 _,f,err:=fixturePath(r);if err!=nil{return err}
 info,err:=os.Lstat(f)
 if err!=nil || !info.Mode().IsRegular(){return errors.New("fixture file invalid")}
 got,err:=os.ReadFile(f);if err!=nil{return err}
 expected:=sha256.Sum256([]byte(r.FileContent));actual:=sha256.Sum256(got)
 if actual!=expected{return errors.New("fixture file digest mismatch")}
 value,err:=regRead(r);if err!=nil{return err}
 if value!=r.RegistryData{return errors.New("registry value mismatch")}
 return nil
}
func install(r Recipe)error{
 dir,f,err:=fixturePath(r);if err!=nil{return err}
 if _,err:=os.Lstat(dir);err==nil{return errors.New("fixture directory exists")}
 if _,err:=regRead(r);err==nil{return errors.New("fixture registry value exists")}
 if err:=os.Mkdir(dir,0700);err!=nil{return errors.New("cannot create fixture directory")}
 if err:=os.WriteFile(f,[]byte(r.FileContent),0600);err!=nil{return errors.New("fixture file write failed")}
 if err:=regWrite(r);err!=nil{return err}
 return verify(r)
}
func uninstall(r Recipe)error{
 dir,f,err:=fixturePath(r);if err!=nil{return err}
 if err:=verify(r);err!=nil{return err}
 items,err:=os.ReadDir(dir)
 if err!=nil || len(items)!=1 || items[0].Name()!=r.FileName || !items[0].Type().IsRegular(){return errors.New("unexpected fixture contents")}
 key,err:=utf16Pointer(r.RegistryKey);if err!=nil{return err}
 result,_,_:=deleteKey.Call(hkcu,uintptr(unsafe.Pointer(key)))
 if result!=0{return errors.New("registry delete failed")}
 if err:=os.Remove(f);err!=nil{return errors.New("file delete failed")}
 if err:=os.Remove(dir);err!=nil{return errors.New("directory delete failed")}
 return nil
}
func main(){
 if os.Getenv("WINEBOT_FIXTURE_PERMIT")!="synthetic-ci" || len(os.Args)!=2{
  fmt.Fprintln(os.Stderr,"RECIPE_REPLAY stage=not_authorized");os.Exit(2)
 }
 r,err:=loadRecipe()
 if err!=nil{fmt.Fprintln(os.Stderr,"RECIPE_REPLAY stage=invalid_recipe");os.Exit(1)}
 var stage string
 switch strings.ToLower(os.Args[1]){
 case "install":stage="installed";err=install(r)
 case "verify":stage="verified";err=verify(r)
 case "uninstall":stage="uninstalled";err=uninstall(r)
 default:stage="invalid";err=errors.New("invalid operation")
 }
 if err!=nil{fmt.Fprintln(os.Stderr,"RECIPE_REPLAY stage=failed");os.Exit(1)}
 fmt.Printf("RECIPE_REPLAY stage=%s\n",stage)
}
