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
  Proof.
    intros n s.
    induction s.
      trivial.
      simpl.
      rewrite IHs.
  Qed.
