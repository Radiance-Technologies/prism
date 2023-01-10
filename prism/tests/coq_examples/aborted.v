(* Adapted from coq/test-suite/success/sideff.v*)
Definition idw (A : Type) := A.
Lemma foobar : unit.
Proof.
  Require Import Program.
  apply (const tt tt).
Abort.

(** Here's a (* nested *) comment *)

Set Nested Proofs Allowed.

Lemma foobar' : unit.
  Lemma aux : forall A : Type, A -> unit.
  Proof. intros. pose (foo := idw A). exact tt. Abort.
  exact tt.
  Lemma aux' : forall A : Type, A -> unit.
  Proof. intros. pose (foo := idw A). exact tt. Qed.
Abort All.


Program Definition foo := let x := _ : unit in _ : x = tt.
Next Obligation.
Abort All.
(* You cannot seem to abort a program's obligations. *)
Next Obligation.
exact tt.
Qed.
Next Obligation.
simpl; match goal with |- ?a = _ => now destruct a end.
Qed.
