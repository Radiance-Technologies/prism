From Coq Require Import String.

Lemma string_app_nil_r (s : string) : (s ++ "")%string = s.
Proof.
  induction s; [ auto | cbn; rewrite IHs; auto ].
Qed.
