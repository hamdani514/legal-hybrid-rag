# Real query review sheet

Generated 2026-10-03T00:01:15 from 77 distinct logged queries (57 need a decision; 20 are pre-filled LEGACY).

## How to fill it in

For each query, edit the `DECISION:` line (and `TYPE:` if the guess is wrong).
Leave DECISION empty to skip a query for now; it stays unlabelled.

| DECISION | meaning |
|---|---|
| `1` | proposed result #1 is THE answer (grade 2) |
| `2` / `3` | proposed result #2 / #3 is the answer |
| `1 3:1` | #1 is the answer, #3 is a relevant alternate (grade 1) |
| `3eff8217` | that judgment (pdf_id prefix, or a filename) is the answer — use when it is not in the top 3 |
| `3eff8217 5a06e4ef:1` | answer plus an alternate, by id |
| `NEG` | out of corpus: the correct behaviour is to abstain |
| `SKIP` | not a real search (greetings, test input); drop it |
| `LEGACY` | already labelled in eval/queries.json; nothing to do |

Below-floor candidates (shown when the system abstained) are numbered too:
`1` then means the first below-floor candidate.

TYPE is one of: citation, entity, statute, issue, paraphrase, disposition, vague, unknown.

When done: `python eval/import_labels.py` then `python eval/build_datasets.py`.

## Judgments in the corpus

| id | file | parties | subject | headnote |
|---|---|---|---|---|
| `d40e2887` | judgement_C_A_1-K_2021.pdf | Usman Ghani v. The Chief Post Master, GPO, Karachi and others | Service law | The appellant, serving as a time scale clerk, sought to set aside the judgment of the Federal Service Tribunal Islamabad (Karachi Bench) which dismissed his service appeal against departmental penalties of increment stop... |
| `49c42cc9` | judgement_C_A_1_2020.pdf | Sardar Abdul Rehman v. Abdul Kareem Kehtran & others | Election law | Abdul Karim Kethran challenged the election of returned candidate Sardar Abdul Rehman in PB-08 Barkhan, Balochistan through an election petition filed by his attorney Sanaullah. The Election Tribunal Balochistan, Quetta ... |
| `3eff8217` | judgement_C_A_23-P_2017.pdf | Pirzada Noor-ul-Basar v. Mst. Pakistan Bibi and others | Property and title | Respondent Mst. Pakistan Bibi sought a declaration that she is the owner of the suit property through a dower deed dated 09.04.1967 against the appellant and others. The Peshawar High Court allowed the civil revision, se... |
| `2df8aea1` | judgement_C_A_26-K_2021.pdf | Abdullah Jumani and others v. Province of Sindh & others | Service law | Appellants sought regularization of their contractual services under the Sindh (Regularization of Adhoc and Contract Employees) Act, 2013 and payment of unpaid salaries by filing constitutional petitions in the High Cour... |
| `3628e429` | judgement_C_A_3-L_2016.pdf | The Inspector General of Police, Punjab & Others v. Waris Ali (deceased) through LRs & Others | Service law | The Inspector General of Police, Punjab & Others appealed against the Punjab Service Tribunal's order dated 04.03.2015 passed in Appeal No.39 of 2014 concerning the service and promotion dispute raised by Waris Ali (dece... |
| `5a06e4ef` | judgement_C_A_42-K_2016.pdf | Manzoor Hussain and another v. Khalid Aziz and others | Property and title | Respondents No. 1 and 2 sought a declaration, permanent injunction, cancellation of documents, possession and mesne profits regarding land situated in Deh and Taluqa Tando Adam, District Sanghar, after discovering that t... |
| `adaeb488` | judgement_C_A_43-Q_2018.pdf | Ghulam Mustafa v. Mst. Mah Begum and others | Land and revenue | The appellant Ghulam Mustafa sought a declaration of ownership, recovery of possession, and permanent injunction against respondents Mst. Mah Begum and others regarding joint property, after a mutation was sanctioned in ... |
| `5a14105d` | judgement_C_A_5-Q_2014.pdf | Mir Saleem Ahmed Khosa v. Zafarullah Khan Jamali and others | Election law | The appellant challenged the victory of respondent No. 1 from National Assembly seat NA-266, Nasirabad-cum-Jaffarabad by filing an election petition under Section 52 of the Representation of the People Act, 1976, allegin... |
| `4083a42e` | judgement_C_A_57-K_2018.pdf | Shezan Services (Private) Limited. v. Shezan Bakers & Confectioners (Private) Limited and another | Intellectual property | Shezan Services (Private) Limited appealed against the High Court of Sindh's judgment dated 14.05.2018, which had upheld the Registrar of Trade Marks' decision in favor of Shezan Bakers & Confectioners (Private) Limited ... |
| `fa86ba1f` | judgement_C_A_6_2016.pdf | Federation of Pakistan through Secretary, Ministry of Foreign Affairs, Islamabad and others v. Ali Naseem | Service tribunal jurisdiction | The Federation of Pakistan through the Secretary, Ministry of Foreign Affairs appealed against the judgments of the Federal Service Tribunal, Islamabad, which had accepted the service appeals of locally employed staff wh... |

## Queries

### real-8fe6bdd397  (asked 17x)

QUERY: evacuee land granted and later disputed in Tando Adam
System top 3:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.997
Already labelled (legacy): `5a06e4ef` judgement_C_A_42-K_2016.pdf
DECISION: LEGACY
TYPE: entity

### real-4b79298b4d  (asked 17x)

QUERY: Is a claim relating to dower within the jurisdiction of a Family Court?
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.907
Already labelled (legacy): `3eff8217` judgement_C_A_23-P_2017.pdf
DECISION: LEGACY
TYPE: issue

### real-1fbf70f728  (asked 14x)

QUERY: did the Service Tribunal have jurisdiction to entertain the service appeal
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 1.000
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.985
  3. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.358
Already labelled (legacy): `d40e2887` judgement_C_A_1-K_2021.pdf
DECISION: LEGACY
TYPE: issue

### real-4ab80f6304  (asked 11x)

QUERY: contempt application dismissed by the High Court of Balochistan
System top 3:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.990
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.936
Already labelled (legacy): `ce086b4a` (not in corpus)
DECISION: LEGACY
TYPE: entity

### real-b8933f5dfb  (asked 10x)

QUERY: agricultural land allotted after partition and the title later questioned
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.002
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.000
Already labelled (legacy): `5a06e4ef` judgement_C_A_42-K_2016.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-8d135c8cbe  (asked 10x)

QUERY: appeal allowed and the impugned judgment set aside with parties bearing their own costs
System top 3:
  1. `49c42cc9` judgement_C_A_1_2020.pdf  score 1.000
  2. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.998
  3. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.997
Already labelled (legacy): `49c42cc9` judgement_C_A_1_2020.pdf
DECISION: LEGACY
TYPE: disposition

### real-06b4f3116a  (asked 10x)

QUERY: appeal dismissed with no order as to costs for want of merit
System top 3:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 1.000
  2. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.984
  3. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.917
Already labelled (legacy): `5a06e4ef` judgement_C_A_42-K_2016.pdf
DECISION: LEGACY
TYPE: disposition

### real-fc82e7e936  (asked 10x)

QUERY: Can rejected ballot papers be recounted after a narrow victory margin?
System top 3:
  1. `49c42cc9` judgement_C_A_1_2020.pdf  score 0.473
DECISION: 
TYPE: issue

### real-fe6bdcbe74  (asked 10x)

QUERY: challenge to a narrow win in a provincial assembly constituency in Balochistan
System top 3:
  1. `49c42cc9` judgement_C_A_1_2020.pdf  score 0.574
Already labelled (legacy): `49c42cc9` judgement_C_A_1_2020.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-8e5b98824e  (asked 10x)

QUERY: civil revision dismissed by the High Court of Balochistan at Quetta
System top 3:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 1.000
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.970
  3. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.934
Already labelled (legacy): `adaeb488` judgement_C_A_43-Q_2018.pdf
DECISION: LEGACY
TYPE: entity

### real-7ff96802c0  (asked 10x)

QUERY: civil servant denied a fair opportunity of hearing by the tribunal
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.879
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.849
Already labelled (legacy): `d40e2887` judgement_C_A_1-K_2021.pdf
DECISION: LEGACY
TYPE: issue

### real-6c8ba995db  (asked 10x)

QUERY: constitutional petitions decided by the High Court of Sindh at Karachi in 2021
System top 3:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.999
  2. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.962
  3. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.874
Already labelled (legacy): `2df8aea1` judgement_C_A_26-K_2021.pdf
DECISION: LEGACY
TYPE: entity

### real-7393246480  (asked 10x)

QUERY: dispute over wrong entries in the revenue record between spouses
System top 3:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.816
Already labelled (legacy): `3eff8217` judgement_C_A_23-P_2017.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-bba332c295  (asked 10x)

QUERY: election petition where the winning margin was only sixty five votes
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.600
  2. `49c42cc9` judgement_C_A_1_2020.pdf  score 0.246
Already labelled (legacy): `49c42cc9` judgement_C_A_1_2020.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-12e8c3c11b  (asked 10x)

QUERY: general elections 2013 National Assembly seat NA-266 Nasirabad Jaffarabad
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 1.000
Already labelled (legacy): `5a14105d` judgement_C_A_5-Q_2014.pdf
DECISION: LEGACY
TYPE: entity

### real-52178cf439  (asked 10x)

QUERY: lower school course dates determining a police officer's seniority
System top 3:
  1. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.769
Already labelled (legacy): `3628e429` judgement_C_A_3-L_2016.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-2ad478b37e  (asked 10x)

QUERY: seniority and promotion of police officers before a service tribunal
System top 3:
  1. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.238
  2. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.225
Already labelled (legacy): `3628e429` judgement_C_A_3-L_2016.pdf
DECISION: LEGACY
TYPE: issue

### real-66c0cd348e  (asked 10x)

QUERY: trade mark assignment agreement was incorrectly relied upon
System top 3:
  1. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.999
Already labelled (legacy): `4083a42e` judgement_C_A_57-K_2018.pdf
DECISION: LEGACY
TYPE: issue

### real-6ada17c7de  (asked 10x)

QUERY: two service appeals raising common questions of law decided together
System top 3:
  1. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.420
Already labelled (legacy): `fa86ba1f` judgement_C_A_6_2016.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-4d05f72637  (asked 10x)

QUERY: when will this Court decline leave to appeal under Article 185(3)
System top 3:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.425
Already labelled (legacy): `ce086b4a` (not in corpus)
DECISION: LEGACY
TYPE: statute

### real-1c79366717  (asked 10x)

QUERY: who owns a brand name after a company is restructured
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.000
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
Already labelled (legacy): `4083a42e` judgement_C_A_57-K_2018.pdf
DECISION: LEGACY
TYPE: paraphrase

### real-612daadf58  (asked 7x)

QUERY: Appeal by Pirzada Noor-ul-Basar against Mst. Pakistan Bibi and others regarding a family dispute under the Family Courts Act, 1964. The Supreme Court held that the Court interpreted the relevant statutory provisions and rules. Appeal dismissed.
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.995
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.883
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.573
DECISION: 
TYPE: statute

### real-707868e56a  (asked 6x)

QUERY: imran khan bail case
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.160
  2. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.035
  3. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.018
DECISION: 
TYPE: vague

### real-0bf5672561  (asked 5x)

QUERY: bail granted despite murder charges
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.000
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.000
DECISION: 
TYPE: disposition

### real-a08ab20753  (asked 5x)

QUERY: bail granted despite murder charges weak evidence
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.000
  2. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.000
  3. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
DECISION: 
TYPE: disposition

### real-0200c4245d  (asked 5x)

QUERY: Co-owners under a family settlement transferring more than their share
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.024
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.000
DECISION: 
TYPE: paraphrase

### real-7c564c3515  (asked 5x)

QUERY: Dispute over evacuee land devolving on legal heirs
System top 3:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.710
DECISION: 
TYPE: paraphrase

### real-d4839bdc6f  (asked 5x)

QUERY: family dispute case
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.045
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.012
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.005
DECISION: 
TYPE: vague

### real-91be4867bf  (asked 5x)

QUERY: Seniority and promotion dispute between police officers
System top 3:
  1. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.392
DECISION: 
TYPE: paraphrase

### real-df5d41b6ec  (asked 5x)

QUERY: Service appeal remanded for fresh hearing after denial of opportunity
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.992
DECISION: 
TYPE: disposition

### real-6becea4518  (asked 5x)

QUERY: service tribunal jurisdiction over a civil servant appeal
System top 3:
  1. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.994
  2. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.966
  3. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.669
DECISION: 
TYPE: paraphrase

### real-47fcd38255  (asked 5x)

QUERY: Was the penalty imposed on the civil servant proportionate to the misconduct?
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.929
DECISION: 
TYPE: issue

### real-d6986f2824  (asked 5x)

QUERY: What did the Court decide about family court jurisdiction under the Family Courts Act 1964?
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.003
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.002
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.002
DECISION: 
TYPE: statute

### real-cef436867c  (asked 4x)

QUERY: family dispute
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.026
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.005
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.002
DECISION: 
TYPE: vague

### real-01f618d859  (asked 4x)

QUERY: Order of the Punjab Service Tribunal set aside on appeal
System top 3:
  1. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.994
  2. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.952
  3. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.924
DECISION: 
TYPE: entity

### real-89a09eddce  (asked 4x)

QUERY: Requirements under the Representation of the People Act for alleging rigging
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.999
DECISION: 
TYPE: statute

### real-95250d05de  (asked 4x)

QUERY: Service dispute involving employees of the Ministry of Foreign Affairs
System top 3:
  1. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.678
DECISION: 
TYPE: entity

### real-39c56dc870  (asked 4x)

QUERY: service tribunal appeal
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.999
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.989
  3. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.605
DECISION: 
TYPE: vague

### real-4fbfc5e215  (asked 4x)

QUERY: What must an election petition plead to establish corrupt practices?
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.999
DECISION: 
TYPE: issue

### real-926fcca2b9  (asked 4x)

QUERY: Wife claiming ownership of land on the basis of a dower deed
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.755
DECISION: 
TYPE: paraphrase

### real-ab0af3d40c  (asked 2x)

QUERY: Appeal against conviction and death sentence for murder
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.004
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.001
  3. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.001
DECISION: 
TYPE: paraphrase

### real-95317ea1a1  (asked 2x)

QUERY: Bail granted in a narcotics possession case
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.002
  2. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.000
  3. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
DECISION: 
TYPE: disposition

### real-97409e68fb  (asked 2x)

QUERY: Can a Single Judge of a High Court exercise suo motu jurisdiction under Article 199?
System top 3:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.997
DECISION: 
TYPE: statute

### real-0fc380c073  (asked 2x)

QUERY: Challenge to the election of a returned candidate before an election tribunal
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.986
  2. `49c42cc9` judgement_C_A_1_2020.pdf  score 0.902
DECISION: 
TYPE: paraphrase

### real-789cd21f31  (asked 2x)

QUERY: Constitutional petitions decided by the High Court of Sindh at Karachi
System top 3:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.998
  2. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.974
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.712
DECISION: 
TYPE: entity

### real-029b5fa672  (asked 2x)

QUERY: Correction of wrong entries in the revenue record
System top 3:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.963
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.961
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.233
DECISION: 
TYPE: paraphrase

### real-8e7277d8ac  (asked 2x)

QUERY: family court jurisdiction under the Family Courts Act 1964
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.003
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.003
  3. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.001
DECISION: 
TYPE: statute

### real-0024604d44  (asked 2x)

QUERY: legal dispute between the families
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.023
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.001
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
DECISION: 
TYPE: paraphrase

### real-23b3df0dfe  (asked 2x)

QUERY: What must an election petition plead to establish corrupt practices and rigging?
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 1.000
DECISION: 
TYPE: issue

### real-2711963520  (asked 2x)

QUERY: Whether the Service Tribunal had jurisdiction to entertain the appeal
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 1.000
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.959
  3. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.253
DECISION: 
TYPE: issue

### real-879f3fe6e7  (asked 2x)

QUERY: Who qualifies as a civil servant under the Service Tribunals Act 1973?
System top 3:
  1. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.999
  2. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.706
  3. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.358
DECISION: 
TYPE: statute

### real-6f945690cb  (asked 2x)

QUERY: Why was bail granted despite murder charges?
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.000
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
  3. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
DECISION: 
TYPE: issue

### real-07a0a20b25  (asked 1x)

QUERY: any family dispute case
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.009
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.004
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.001
DECISION: 
TYPE: vague

### real-bda1c7dd7e  (asked 1x)

QUERY: bail granted to accused in a murder case
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.001
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
  3. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.000
DECISION: 
TYPE: disposition

### real-b86f1a8200  (asked 1x)

QUERY: case of car selling
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.005
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
  3. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.000
DECISION: 
TYPE: vague

### real-9f8aecaf5d  (asked 1x)

QUERY: Case where accused got bail in a murder case 2019, bail was granted
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.001
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.000
  3. `49c42cc9` judgement_C_A_1_2020.pdf  score 0.000
DECISION: 
TYPE: disposition

### real-42007fa3c6  (asked 1x)

QUERY: civil servant appeal against dismissal before the Service Tribunal
System top 3:
  1. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.993
  2. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.976
DECISION: 
TYPE: entity

### real-8ef3288da7  (asked 1x)

QUERY: cryptocurrency regulation in Europe
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.000
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.000
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
DECISION: 
TYPE: vague

### real-92cfd862fe  (asked 1x)

QUERY: cryptocurrency regulation in the European Union
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.000
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.000
  3. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.000
DECISION: 
TYPE: entity

### real-ccd4d9be01  (asked 1x)

QUERY: dispute on car
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.002
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
  3. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.000
DECISION: 
TYPE: vague

### real-92e8454dd5  (asked 1x)

QUERY: election petition alleging rigging by the returned candidate
System top 3:
  1. `5a14105d` judgement_C_A_5-Q_2014.pdf  score 0.999
  2. `49c42cc9` judgement_C_A_1_2020.pdf  score 0.954
DECISION: 
TYPE: paraphrase

### real-f662533d12  (asked 1x)

QUERY: family court jurisdiction dower deed
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.501
DECISION: 
TYPE: paraphrase

### real-3226c5c968  (asked 1x)

QUERY: got it
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.004
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.003
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.003
DECISION: 
TYPE: vague

### real-f6ec7e183b  (asked 1x)

QUERY: goveronment of pakistan vs pso
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.051
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.038
  3. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.016
DECISION: 
TYPE: entity

### real-c22b5f9178  (asked 1x)

QUERY: hi
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.002
  2. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.002
  3. `4083a42e` judgement_C_A_57-K_2018.pdf  score 0.002
DECISION: 
TYPE: vague

### real-b6f1287842  (asked 1x)

QUERY: hiiii
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.001
  2. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.001
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
DECISION: 
TYPE: vague

### real-8696220609  (asked 1x)

QUERY: legal dispute
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.393
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.393
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.245
DECISION: 
TYPE: vague

### real-b3bd2b034b  (asked 1x)

QUERY: legal dispute case
System top 3:
  1. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.366
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.253
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.253
DECISION: 
TYPE: vague

### real-dad172f144  (asked 1x)

QUERY: legal issue
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.998
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.998
  3. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.995
DECISION: 
TYPE: vague

### real-ddbce45db7  (asked 1x)

QUERY: okyyyy
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.000
  2. `5a06e4ef` judgement_C_A_42-K_2016.pdf  score 0.000
  3. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.000
DECISION: 
TYPE: vague

### real-113b6dbf15  (asked 1x)

QUERY: police officer removed from service after departmental inquiry
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.932
DECISION: 
TYPE: paraphrase

### real-f03706ae6d  (asked 1x)

QUERY: postal department employee seeking reinstatement and back benefits
System: ABSTAINED (nothing above the relevance floor).
Below-floor candidates:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.001
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.000
  3. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.000
DECISION: 
TYPE: paraphrase

### real-91dc9f287b  (asked 1x)

QUERY: Regularisation of contractual employees under a provincial 2013 Act
System top 3:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.999
DECISION: 
TYPE: statute

### real-ad301dd6d0  (asked 1x)

QUERY: service tribunal
System top 3:
  1. `d40e2887` judgement_C_A_1-K_2021.pdf  score 0.995
  2. `fa86ba1f` judgement_C_A_6_2016.pdf  score 0.984
  3. `3628e429` judgement_C_A_3-L_2016.pdf  score 0.885
DECISION: 
TYPE: vague

### real-b49b314472  (asked 1x)

QUERY: suit for possession of property decided in civil revision
System top 3:
  1. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.992
  2. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.949
DECISION: 
TYPE: paraphrase

### real-738390314a  (asked 1x)

QUERY: suit for possession, civil revision
System top 3:
  1. `adaeb488` judgement_C_A_43-Q_2018.pdf  score 0.918
  2. `3eff8217` judgement_C_A_23-P_2017.pdf  score 0.907
DECISION: 
TYPE: paraphrase

### real-9bafe24577  (asked 1x)

QUERY: suo motu jurisdiction under Article 199
System top 3:
  1. `2df8aea1` judgement_C_A_26-K_2021.pdf  score 0.999
DECISION: 
TYPE: statute

