(*
Test heuristic parsing of notations.
These sample notations are taken from coqeal/refinements/refinements.v.
This file is not meaant to be executable.
*)

Notation "0"      := zero_op        : computable_scope.
Notation "1"      := one_op         : computable_scope.
Notation "-%C"    := opp_op.
Notation "- x"    := (opp_op x)     : computable_scope.
Notation "+%C"    := add_op.
Notation "x + y"  := (add_op x y)   : computable_scope.
Notation "x - y"  := (sub_op x y)   : computable_scope.
Notation "*%C"    := mul_op.
Notation "x * y"  := (mul_op x y)   : computable_scope.
Notation "x ^ y"  := (exp_op x y)   : computable_scope.
Notation "x %/ y" := (div_op x y)   : computable_scope.
Notation "x ^-1"  := (inv_op x)     : computable_scope.
Notation "x %% y" := (mod_op x y)   : computable_scope.
Notation "*:%C"   := scale_op.
Notation "x *: y" := (scale_op x y) : computable_scope.
Notation "x == y" := (eq_op x y)    : computable_scope.
Notation "x <= y" := (leq_op x y)   : computable_scope.
Notation "x < y"  := (lt_op x y)    : computable_scope.
Notation cast     := (@cast_op _).

Tactic Notation  "context" "[" ssrpatternarg(pat) "]" tactic3(tac) :=
  let H := fresh "H" in let Q := fresh "Q" in let eqQ := fresh "eqQ" in
  ssrpattern pat => H;
  elim/abstract_context : (H) => Q eqQ; rewrite /H {H};
  tac; rewrite eqQ {Q eqQ}.


Notation "'[' 'coqeal'  strategy  'of'  x ']'" :=
  (@coqeal_eq strategy _ _ _ _ x _ _ _ _ _ _).
Notation coqeal strategy := [coqeal strategy of _].
Notation "'[' 'coqeal'  strategy  'of'  x  'for'  y ']'" :=
  ([coqeal strategy of x] : y = _).

Tactic Notation "coqeal_" tactic3(tac) :=  apply: refines_goal; tac.
Tactic Notation "coqeal" "[" ssrpatternarg(pat) "]" open_constr(strategy) :=
  let H := fresh "H" in let Q := fresh "Q" in let eqQ := fresh "eqQ" in
  ssrpattern pat => H; elim/abstract_context : (H) => Q eqQ;
  rewrite /H {H} [(X in Q X)](coqeal strategy) eqQ {Q eqQ}.

(* Some extra challenging notations. *)
Notation "a := b" := (a <> string_dec "asd" <> b) (at level 60).
Notation "a ;; b" := (a := string_dec "asd" := b) (at level 50).
Notation """a""" := (string_dec """" <> a <> string_dec """") (at level 70).
