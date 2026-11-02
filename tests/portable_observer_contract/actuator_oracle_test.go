package observercontract

import (
 "errors"
 "testing"
)

func TestActuatorAuthorizationNegativeMatrix(t *testing.T) {
 a:=Authority{Principal:"controller",Desktop:"desktop-1",LeaseEpoch:7,TargetRef:"opaque-1",TargetEpoch:11,Allowed:map[string]bool{"window.activate":true}}
 good:=Proposal{Principal:"controller",Desktop:"desktop-1",LeaseEpoch:7,TargetRef:"opaque-1",TargetEpoch:11,Operation:"window.activate"}
 if err:=ValidateProposal(good,a);err!=nil {t.Fatal(err)}
 cases:=[]struct{name string;modify func(*Proposal);want error}{
  {"principal",func(p *Proposal){p.Principal="other"},ErrUnauthorized},
  {"desktop",func(p *Proposal){p.Desktop="desktop-2"},ErrUnauthorized},
  {"lease ABA",func(p *Proposal){p.LeaseEpoch=6},ErrLeaseConflict},
  {"lease missing",func(p *Proposal){p.LeaseEpoch=0},ErrLeaseConflict},
  {"target ABA",func(p *Proposal){p.TargetEpoch=10},ErrStaleTarget},
  {"target mismatch",func(p *Proposal){p.TargetRef="opaque-2"},ErrStaleTarget},
  {"unknown operation",func(p *Proposal){p.Operation="process.kill"},ErrUnauthorized},
  {"missing principal",func(p *Proposal){p.Principal=""},ErrUnauthorized},
 }
 for _,tc:=range cases {t.Run(tc.name,func(t *testing.T){p:=good;tc.modify(&p);if err:=ValidateProposal(p,a);!errors.Is(err,tc.want){t.Fatalf("got %v want %v",err,tc.want)}})}
}
func TestPostconditionUnknownIsNotSuccess(t *testing.T) {
 for _,tc:=range []struct{observed,expected string;current bool}{
  {"active","active",false},{"inactive","active",true},{"","active",true},{"active","",true},
 } {if err:=VerifyPostcondition(tc.observed,tc.expected,tc.current);!errors.Is(err,ErrOutcomeUnknown){t.Fatalf("unsafe success: %+v",tc)}}
 if err:=VerifyPostcondition("active","active",true);err!=nil {t.Fatal(err)}
}
