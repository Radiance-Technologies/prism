(* Adapted from coq/test-suite/success/sideff.v*)
Definition idw (A : Type) := A.
Lemma foobar : unit.
Proof.
  Require Import Program.
  apply (const tt tt).
Qed.

(** Here's a (* nested *) comment *)

Set Nested Proofs Allowed.

Lemma foobar' : unit.
  Lemma aux : forall A : Type, A -> unit.
  Proof. intros. pose (foo := idw A). exact tt. Qed.
  apply (@aux unit tt).
Qed.
Check foobar'.
