Require Coq.Program.Tactics.
Require Coq.derive.Derive.
Require Import Coq.Numbers.Natural.Peano.NPeano.

Set Nested Proofs Allowed.

Section P.

Variables (n m k:nat).

(* A plugin-based proof environment. *)
Derive p SuchThat ((k*n)+(k*m) = p) As h.
rewrite <- Nat.mul_add_distr_l.
subst p.
reflexivity.
Qed.

(* A simple example showing that proofs may be interleaved. *)
Program Definition foo := let x := _ : unit in _ : x = tt.
(* Start first obligation of foo *)
Next Obligation.
(* Interject with new conjecture. *)
Definition foobar : unit.
Proof.
exact tt.
(* Switch back to first obligation of foo *)
Next Obligation.
exact tt.
Qed.
(* Finish proof of foobar *)
Defined.
(* Start next obligation of foo *)
Next Obligation.
simpl; match goal with |- ?a = _ => now destruct a end.
Qed.
(* We accidentally revealed a bug in Coq.
   foo is defined but we are back in its first (proved) obligation.
   The Abort. gets us back to a stable(?) state. *)
Fail Qed.
Abort.

Obligation Tactic := try (exact tt); try (simpl; match goal with |- ?a = _ => now destruct a end).

Program Definition foo' := let x := _ : unit in _ : x = tt.
