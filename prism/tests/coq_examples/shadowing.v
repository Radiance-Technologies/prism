(* Examples of shadowed definitions. *)

(**
Shadow a  global definition.
Also serves as edge case for a definition referencing what it shadows.
*)
Fixpoint nat (n m:nat) {struct n} : nat :=
match n with
| O => m
| S p => S (nat p m)
end.
