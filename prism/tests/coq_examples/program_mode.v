Set Program Mode.

Require Coq.Program.Tactics.
Require Coq.derive.Derive.
Require Import Coq.Numbers.Natural.Peano.NPeano.

Section P.

Variables (n m k:nat).

(* A plugin-based proof environment. *)
Derive p SuchThat ((k*n)+(k*m) = p) As h.
rewrite <- Nat.mul_add_distr_l.
subst p.
reflexivity.
Qed.

Fixpoint add (n' m:nat) {struct n'} : nat :=
match n' with
| O => m
| S p => S (add p m)
end.

(* A simple example showing that proofs may be interleaved. *)
Definition foo := let x := _ : unit in _ : x = tt.
(* Start first obligation of foo *)
Next Obligation.
(* Switch back to first obligation of foo *)
exact tt.
Qed.
(* Start next obligation of foo *)
Next Obligation.
simpl; match goal with |- ?a = _ => now destruct a end.
Qed.

Obligation Tactic := try (exact tt); try (simpl; match goal with |- ?a = _ => now destruct a end).

Definition foo' := let x := _ : unit in _ : x = tt.
