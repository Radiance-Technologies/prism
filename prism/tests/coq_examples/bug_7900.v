(* Reproduced from coq/test-suite/bugs/bug_7900.v *)
Require Import Coq.Program.Program.
(* Set Universe Polymorphism. *)
Set Printing Universes.

Axiom ALL : forall {T:Prop}, T.

Inductive Expr : Set := E (a : Expr).

Parameter Value : Set.

Fixpoint eval (e: Expr): Value :=
  match e with
  | E a => eval a
  end.

Class Quote (n: Value) : Set :=
  { quote: Expr
    ; eval_quote: eval quote = n }.

(* The rewrite introduces an identifier as a side-effect. *)
Program Definition quote_mult n
        `{!Quote n} : Quote n :=
  {| quote := E (quote (n:=n)) |}.

Set Printing Universes.
Next Obligation.
Proof.
  Show Universes.
  destruct Quote0 as [q eq].
  Show Universes.
  rewrite <- eq.
  clear n eq.
  Show Universes.
  apply ALL.
  Show Universes.
Qed.
