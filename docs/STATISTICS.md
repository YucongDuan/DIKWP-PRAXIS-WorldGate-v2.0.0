# Sequential monitoring contract

For group failures X_g in {0,1}, the null is the *conditional* bound P(X_g=1 | past) <= p0. For each predeclared q > p0, define L_t(q) = product over g of (q/p0)^X_g ((1-q)/(1-p0))^(1-X_g). The equal-weight finite mixture E_t is a nonnegative test supermartingale with E_0=1 under the stated null. A threshold 1/alpha controls crossing probability by Ville's inequality. This is an application of established safe anytime-valid inference [S4], not a newly discovered theorem.

For multiple predeclared streams, the implementation uses alpha_stream = family_alpha / family_size. Union-bound control does not require independence between the streams, but the declared family must include all tests. Alternatives, ordering, family and p0 cannot be tuned after looking at outcomes. Group labels alone do not prove that the conditional null or population sampling assumptions are justified.

Missing outcomes stop the resolved *ordered prefix*. Later completed observations are not promoted ahead of pending groups. No rejection is NOT a safety certificate. The fixed mixture is not guaranteed to detect every late shift quickly, and no effect-size confidence interval or adaptive restart policy is supplied. Any immediate hard incident may require suspension without waiting for a statistical alarm.

The reference parameters p0=.05, alternatives [.1,.2,.4,.7], family_alpha=.05 and family_size=2 are synthetic teaching settings, not an industry risk standard. A 25-group stream with ten nonfailures followed by fifteen failures first crosses its threshold of 40 at group 15. A missing sixth outcome leaves only five processed groups. These are computation checks, not measured production risk.

The v1 fixed-sample cluster bootstrap, Wilson intervals and judge audits are retained under the legacy package. Their assumptions have not been replaced by this sequential monitor.
