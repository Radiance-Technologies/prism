(* Examples of shadowed definitions. *)

(**
Shadow a  global definition.
Also serves as edge case for a definition referencing what it shadows.
*)
Fixpoint nat (n' m:nat) {struct n'} : nat :=
match n' with
| O => m
| S p => S (nat p m)
end.

Section nat.

Lemma plus_0_n : forall n : Datatypes.nat, nat 0 n = n.
Proof.
intros m.
simpl.
reflexivity.
Qed.

End nat.
