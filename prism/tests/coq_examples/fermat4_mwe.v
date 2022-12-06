Require Export Wf_nat.
Require Export ZArith.
Require Export Znumtheory.
Require Export Reals.
Open Scope Z_scope.
Definition f_Z (x : Z) := Z.abs_nat x.
Definition R_prime (x y : Z) := 1 < x /\ 1 < y /\ x < y.
Lemma R_prime_wf : well_founded R_prime.
Proof.
  apply (well_founded_lt_compat _ f_Z R_prime); unfold R_prime, f_Z; intros;
    apply Zabs_nat_lt; intuition.
Qed.
Lemma ind_prime : forall P : Z -> Prop,
  (forall x : Z, (forall y : Z, (R_prime y x -> P y)) -> P x) ->
  forall x : Z, P x.
Proof.
  intros; generalize (well_founded_ind R_prime_wf P); auto.
Qed.
Lemma not_rel_prime1 : forall x y : Z,
  ~ rel_prime x y -> exists d : Z, Zis_gcd x y d /\ d <> 1 /\ d <> -1.
Proof.
  unfold rel_prime; intros; elim (Zgcd_spec x y); intros; elim p; clear p;
    intros; exists x0; split;
      [ assumption
      | split;
        [ elim (Z.eq_dec x0 1); intro; [ rewrite a in H0; auto | assumption ]
        | elim (Z.eq_dec x0 (-1)); intro;
          [ rewrite a in H0; generalize (Zis_gcd_opp _ _ _ H0); simpl;
            clear H0; intro; generalize (Zis_gcd_sym _ _ _ H0); auto
          | assumption ] ] ].
Qed.
Lemma Zmult_neq_0 : forall a b : Z, a * b <> 0 -> a <> 0 /\ b <> 0.
Proof.
  intros; elim (Z.eq_dec a 0); intro;
    [ rewrite a0 in H; simpl in H; auto
    | elim (Z.eq_dec b 0); intro; try (rewrite a0 in H;
      rewrite Zmult_comm in H; simpl in H); auto ].
Qed.
Lemma not_prime_gen : forall a b : Z, 1 < a -> 1 < b -> b < a -> ~ prime a ->
  (forall c : Z, b < c < a -> rel_prime c a) ->
  exists q : Z, exists b : Z, a = q * b /\ 1 < q /\ 1 < b.
Proof.
  induction b using ind_prime; intros.
  destruct (Zdivide_dec b a) as [(q,H5)|n].
  - exists q; exists b; intuition;
    apply (Zmult_gt_0_lt_reg_r 1 q b); auto with zarith.
  - case (rel_prime_dec b a); intro.
    * case (Z.eq_dec b 2); intro.
      + absurd (prime a); try assumption.
        apply prime_intro; auto; rewrite e in H4; rewrite e in r;
        generalize (rel_prime_1 a); intros; case (Z.eq_dec n0 1); intro;
        try (rewrite e0; assumption); case (Z.eq_dec n0 2); intro;
        try (rewrite e0; assumption); apply H4; auto with zarith.
      + assert (R_prime (b - 1) b) by (unfold R_prime; intuition).
        assert (1 < b - 1) by auto with zarith.
        assert (b - 1 < a) by auto with zarith.
        assert (forall c : Z, (b - 1) < c < a -> rel_prime c a)
        by (intros; case (Z.eq_dec c b); intro;
            try (rewrite e; assumption);
            apply H4; auto with zarith).
        elim (H _ H5 H0 H6 H7 H3 H8); intros; elim H9; clear H9; intros;
        exists x; exists x0; intuition.
    * elim (not_rel_prime1 _ _ n0); clear n0; intros;
      do 2 (elim H5; clear H5; intros); elim H6; clear H6; intros;
      destruct H7 as (q,H7).
      assert (x <> 0)
      by (assert (a <> 0) by auto with zarith; rewrite H7 in H10;
          elim (Zmult_neq_0 _ _ H10); auto).
      case (Z_le_dec 0 x); intro.
      + exists q; exists x; intuition; rewrite H7 in H0.
        assert (0 < q * x) by auto with zarith.
        assert (0 < x) by auto with zarith.
        generalize (Zmult_lt_0_reg_r _ _ H12 H11); intro;
        case (Z.eq_dec q 1); auto with zarith; intro; elimtype False;
        rewrite e in H7; rewrite Zmult_1_l in H7; destruct H5 as (q0,H5);
        rewrite H5 in H1; cut (0 < q0 * x); auto with zarith;
        intro; generalize (Zmult_lt_0_reg_r _ _ H12 H14); intro;
        rewrite H7 in H2; rewrite <- (Zmult_1_l x) in H2;
        rewrite H5 in H2; generalize (Zmult_lt_reg_r _ _ _ H12 H2);
        auto with zarith.
      + exists (-q); exists (-x); intuition; try (rewrite H7; ring);
        rewrite H7 in H0; replace (q * x) with (-q * -x) in H0 by ring.
        assert (0 < -q * -x) by auto with zarith.
        assert (0 < -x) by auto with zarith.
        generalize (Zmult_lt_0_reg_r _ _ H12 H11);
        intro; case (Z.eq_dec q (-1)); auto with zarith; intro;
        elimtype False; rewrite e in H7; rewrite Zmult_comm in H7;
        rewrite <- Zopp_eq_mult_neg_1 in H7; destruct H5 as (q0,H5);
        replace (q0 * x) with (-q0 * -x) in H5 by ring;
        rewrite H5 in H1;
        assert (0 < -q0 * -x) by auto with zarith;
        generalize (Zmult_lt_0_reg_r _ _ H12 H14); intro;
        rewrite <- (Zmult_1_l a) in H2; rewrite H7 in H2; rewrite H5 in H2;
        generalize (Zmult_lt_reg_r _ _ _ H12 H2); auto with zarith.
Qed.

Lemma prime_dec_gen : forall a b : Z, 1 < b -> b < a ->
  (forall c : Z, b < c < a -> rel_prime c a) -> prime a \/ ~ prime a.
Proof.
  intros a b; pattern b;
    match goal with
    | |- (?p _) =>
      simpl; case (Z_lt_dec 1 a); intro; try (right; red; intro; elim H2;
      clear H2; intros; progress auto); apply (ind_prime p); intros;
      case (rel_prime_dec x a); intro;
        [ case (Z.eq_dec x 2); intro;
          [ left; rewrite e in H2; rewrite e in r; generalize (rel_prime_1 a);
            intro; apply prime_intro; try assumption; intros;
            case (Z.eq_dec n 1); intro; try (rewrite e0; assumption);
            case (Z.eq_dec n 2); intro; try (rewrite e0; assumption); apply H2;
            auto with zarith
          | apply (H (x - 1)); try unfold R_prime; auto with zarith; intros;
            case (Z.eq_dec c x); intro; try (rewrite e; assumption); apply H2;
            auto with zarith ]
        | right; red; intro; elim H3; clear H3; intros; cut (1 <= x < a);
          auto with zarith; intro; generalize (H4 _ H5); auto ]
    end.
Qed.

Lemma prime_dec : forall a : Z, prime a \/ ~ prime a.
Proof.
  intros; case (Z.eq_dec a 2); intro;
    [ left; rewrite e; apply prime_2
    | case (Z_lt_dec 1 a); intro; try (right; red; intro; elim H; clear H;
      intros; progress auto); apply (prime_dec_gen a (a - 1));
      auto with zarith; intros; elimtype False; auto with zarith ].
Qed.
