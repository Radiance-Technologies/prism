(* An example program with multiple obligations that gets defined
in one step. *)

Require Import Coq.Program.Tactics.

Program Definition foo := let x := _ : unit in _ : x = tt.
Solve All Obligations with try exact tt; simpl; match goal with |- ?a = _ => now destruct a end.
