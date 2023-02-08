(* Verify unnamed proofs (Goals) can be saved and identified afterward
   with Save. *)

Variables A B C D E : Prop.

Goal (A -> B -> C) -> (A -> B) -> A -> C.
  intro H.
  intros H' HA.
  apply H.
  exact HA.
  apply H'.
  assumption.
Save foobat.

Set Nested Proofs Allowed.

Lemma foobar: (A -> B -> C) -> (A -> B) -> A -> C.
  intro H.
  intros H' HA.
  apply H.
  Goal (D -> E) -> D -> E.
    intro G.
    apply G.
  Save foobaz.
  exact HA.
  apply H'.
  assumption.
Qed.
