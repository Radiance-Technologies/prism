(* *********************************************************************)
(*                                                                     *)
(*              A simple test file                                     *)
(*                                                                     *)
(*          John Doe, XYZ Institute                                    *)
(*                                                                     *)
(*  Copyright Foo Bar Baz, Inc.                                        *)
(*  All rights reserved.  This file is distributed                     *)
(*  under the terms of a non-existent license agreement                *)
(*                                                                     *)
(* *********************************************************************)

(** Here's another comment *)

Inductive seq : nat -> Set :=
  | niln : seq 0
  | consn : forall n : nat, nat -> seq n -> seq (S n).

Fixpoint length (n : nat) (s : seq n) {struct s} : nat :=
  match s with
  | niln => 0
  | consn i _ s' => S (length i s')
  end.

Theorem length_corr : forall (n : nat) (s : seq n), length n s = n.
  About seq.
  intros n s.
  Check n.
  Proof.
  induction s...
  Print length.
  - trivial.
  -+{*{{
    simpl.
    rewrite IHs;
    reflexivity...
    } }}
Qed.
Check length_corr.
