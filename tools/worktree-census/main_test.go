// SPDX-License-Identifier: MIT
// Synthetic temporary-repository tests; no access to host/user worktrees.
package main

import (
  "encoding/json"
  "os"
  "os/exec"
  "path/filepath"
  "strings"
  "testing"
)

func runGit(t *testing.T,repo string,args ...string) {
  t.Helper()
  cmd:=exec.Command("git",append([]string{"-C",repo},args...)...)
  if out,err:=cmd.CombinedOutput();err!=nil {
    // Synthetic-only inputs. Do not reproduce user paths in diagnostics.
    t.Fatalf("synthetic Git command failed: %v, %d bytes",err,len(out))
  }
}
func TestWorktreeCensusIsPathRedactedAndReadOnly(t *testing.T) {
  root:=filepath.Join(t.TempDir(),"synthetic-main")
  if err:=os.MkdirAll(root,0700);err!=nil {t.Fatal(err)}
  runGit(t,root,"init","-q")
  runGit(t,root,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-qm","baseline","--allow-empty")
  secondary:=filepath.Join(t.TempDir(),"synthetic-second")
  runGit(t,root,"worktree","add","-q","-b","fixture-second",secondary,"HEAD")
  // Deliberately dirty only the first synthetic worktree.
  if err:=os.WriteFile(filepath.Join(root,"synthetic-untracked-name.txt"),[]byte("fixture"),0600);err!=nil {t.Fatal(err)}
  runGit(t,root,"worktree","lock","--reason","synthetic-test-lock",secondary)
  got,err:=census(root,false)
  if err!=nil {t.Fatal(err)}
  if got.Partial || got.Ownership!="unverified" || len(got.Worktrees)!=2 {
    t.Fatalf("unexpected inventory metadata: partial=%v count=%d",got.Partial,len(got.Worktrees))
  }
  if got.Worktrees[0].Slot!=1 || !got.Worktrees[0].Dirty ||
     got.Worktrees[1].Dirty || !got.Worktrees[1].Locked {
    t.Fatal("dirty/locked status classification failed")
  }
  for _,w:=range got.Worktrees {
    if w.Branch!="" || !w.HasBranch || w.ScanStatus!="read_only_complete" || w.Head=="" {
      t.Fatal("unredacted or missing worktree state")
    }
  }
  result,err:=json.Marshal(got)
  if err!=nil {t.Fatal(err)}
  for _,forbidden:=range []string{root,secondary,"synthetic-untracked-name.txt","synthetic-test-lock"} {
    if strings.Contains(string(result),forbidden) {t.Fatal("private path/name/reason emitted")}
  }
  // The audit must not alter refs, lock metadata or remove dirty files.
  checked,err:=census(root,true)
  if err!=nil {t.Fatal(err)}
  if checked.Worktrees[0].Head!=got.Worktrees[0].Head ||
     checked.Worktrees[1].Head!=got.Worktrees[1].Head ||
     !checked.Worktrees[0].Dirty || !checked.Worktrees[1].Locked {
    t.Fatal("read-only repeat produced unexpected state change")
  }
  if checked.Worktrees[0].Branch=="" || checked.Worktrees[1].Branch=="" {
    t.Fatal("explicit branch-ref opt-in failed")
  }
  if _,err:=os.Stat(filepath.Join(root,"synthetic-untracked-name.txt"));err!=nil {
    t.Fatal("read-only inventory deleted synthetic untracked content")
  }
}
func TestWorktreePorcelainRejectsMalformedInput(t *testing.T) {
  cases:=[][]byte{
    nil,[]byte("HEAD unreachable\x00\x00"),
    []byte("worktree /synthetic\x00HEAD nope\x00\x00"),
    []byte("worktree /synthetic\x00unknown-field secret\x00\x00"),
    []byte("worktree /synthetic\x00HEAD 0000000000000000000000000000000000000000\x00"),
  }
  for _,blob:=range cases {
    if _,err:=parseWorktrees(blob,false);err==nil {t.Fatal("malformed output accepted")}
  }
}
