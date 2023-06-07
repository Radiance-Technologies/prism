From Coq Require Import ssreflect ssrfun ssrbool.

Definition foo : True.
(* abstract emits a foo_subproof identifier *)
abstract exact I.
Defined.

Definition bar : True.
(* transparent_abstract emits a bar_subterm identifier *)
transparent_abstract exact I.
Defined.

Lemma baz : True.
Proof.
(* In certain versions of Coq (namely 8.12.2), the following tactic
emits a legacy_pe_subproof identifier rather than the expected
baz_subproof. *)
have isF' : injective negb by abstract exact: can_inj negbK.
trivial.
Defined.
