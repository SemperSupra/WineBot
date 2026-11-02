// SPDX-License-Identifier: MIT
// Offline, read-only Git worktree inventory for authorized local executors.
// Never emits filesystem paths, filenames, lock reasons, remote URLs or secrets.
// Does not delete, prune, checkout, fetch, pull, clean, reset or modify refs.
package main

import (
  "bytes"
  "encoding/json"
  "errors"
  "flag"
  "fmt"
  "os"
  "os/exec"
  "strings"
)

type worktree struct {
  Path string `json:"-"`
  Slot int `json:"slot"`
  Head string `json:"head,omitempty"`
  Branch string `json:"branch_ref,omitempty"`
  HasBranch bool `json:"has_branch"`
  Detached bool `json:"detached"`
  Bare bool `json:"bare"`
  Locked bool `json:"locked"`
  Prunable bool `json:"prunable"`
  Dirty bool `json:"dirty"`
  ScanStatus string `json:"scan_status"`
}

type inventory struct {
  Contract string `json:"contract"`
  BranchNamesIncluded bool `json:"branch_names_included"`
  Worktrees []worktree `json:"worktrees"`
  Partial bool `json:"partial"`
  Ownership string `json:"actor_ownership"`
}

func gitAt(path string, args ...string) ([]byte,error) {
  arguments:=append([]string{"-c","core.fsmonitor=false","-C",path},args...)
  cmd:=exec.Command("git",arguments...)
  cmd.Env=append(os.Environ(),"GIT_OPTIONAL_LOCKS=0","GIT_TERMINAL_PROMPT=0")
  // Never forward stderr: it could contain filesystem paths or private data.
  return cmd.Output()
}

func parseWorktrees(data []byte,includeBranch bool) ([]worktree,error) {
  var entries []worktree
  var cur *worktree
  for _,raw:=range bytes.Split(data,[]byte{0}) {
    if len(raw)==0 {
      if cur!=nil {
        cur.Slot=len(entries)+1
        cur.ScanStatus="not_scanned"
        entries=append(entries,*cur)
        cur=nil
      }
      continue
    }
    line:=string(raw)
    if strings.HasPrefix(line,"worktree ") {
      if cur!=nil {return nil,errors.New("malformed_worktree_record")}
      cur=&worktree{Path:strings.TrimPrefix(line,"worktree ")}
      if cur.Path=="" {return nil,errors.New("missing_worktree_location")}
      continue
    }
    if cur==nil {return nil,errors.New("malformed_worktree_record")}
    switch {
    case strings.HasPrefix(line,"HEAD "):
      head:=strings.TrimPrefix(line,"HEAD ")
      if len(head)!=40 && len(head)!=64 {return nil,errors.New("invalid_head")}
      for _,c:=range head {if !strings.ContainsRune("0123456789abcdef",c) {return nil,errors.New("invalid_head")}}
      cur.Head=head
    case strings.HasPrefix(line,"branch "):
      cur.HasBranch=true
      if includeBranch {cur.Branch=strings.TrimPrefix(line,"branch ")}
    case line=="detached":
      cur.Detached=true
    case line=="bare":
      cur.Bare=true
    case line=="locked" || strings.HasPrefix(line,"locked "):
      cur.Locked=true
    case line=="prunable" || strings.HasPrefix(line,"prunable "):
      cur.Prunable=true
    default:
      return nil,errors.New("unknown_worktree_record")
    }
  }
  if cur!=nil {return nil,errors.New("unterminated_worktree_record")}
  if len(entries)==0 {return nil,errors.New("no_worktrees")}
  return entries,nil
}

func census(repo string,includeBranch bool) (inventory,error) {
  result:=inventory{Contract:"winebot.worktree.census.v0",BranchNamesIncluded:includeBranch,
    Ownership:"unverified",Worktrees:[]worktree{}}
  data,err:=gitAt(repo,"worktree","list","--porcelain","-z")
  if err!=nil {return result,errors.New("worktree_listing_unavailable")}
  entries,err:=parseWorktrees(data,includeBranch)
  if err!=nil {return result,err}
  for _,w:=range entries {
    if w.Bare {w.ScanStatus="bare_not_scanned";result.Worktrees=append(result.Worktrees,w);continue}
    status,err:=gitAt(w.Path,"status","--porcelain=v1","-z","--untracked-files=normal")
    if err!=nil {
      w.ScanStatus="unavailable"
      result.Partial=true
    } else {
      w.ScanStatus="read_only_complete"
      w.Dirty=len(status)>0
    }
    result.Worktrees=append(result.Worktrees,w)
  }
  return result,nil
}

func main() {
  repo:=flag.String("repo",".","Path to local Git checkout (never emitted)")
  include:=flag.Bool("include-branch-refs",false,"Opt in to emitting branch refs to a PRIVATE evidence destination")
  flag.Parse()
  result,err:=census(*repo,*include)
  if err!=nil {
    // No raw error, paths, remote URLs or filenames are exposed.
    fmt.Fprintln(os.Stderr,"FAIL: worktree_census_unavailable")
    os.Exit(2)
  }
  enc:=json.NewEncoder(os.Stdout)
  enc.SetIndent("","  ")
  if err:=enc.Encode(result);err!=nil {os.Exit(2)}
  if result.Partial {os.Exit(3)}
}
