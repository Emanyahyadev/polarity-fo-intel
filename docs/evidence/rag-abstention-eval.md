# RAG grounding & abstention evaluation

Dataset: 55 validated records. Abstention threshold: min cosine 0.68.

## Q: single-family offices in Texas
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 1 matching family office in the verified dataset:

## Q: multi-family offices
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 5 matching family offices in the verified dataset:

## Q: family offices in Florida
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 5 matching family offices in the verified dataset:

## Q: family offices in New York
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 5 matching family offices in the verified dataset:

## Q: single-family offices in Belgium
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 1 matching family office in the verified dataset:

## Q: family offices in France
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 1 matching family office in the verified dataset:

## Q: family offices in Denmark
- expected: answer · got: answer · ✓ · mode=extractive · matched an authoritative metadata filter (state/country/type/AUM)
- Found 1 matching family office in the verified dataset:

## Q: Pathstone
- expected: answer · got: answer · ✓ · mode=extractive · top similarity 0.72
- Found 1 matching family office in the verified dataset:

## Q: family offices focused on private equity
- expected: answer · got: answer · ✓ · mode=extractive · top similarity 0.77
- Found 5 matching family offices in the verified dataset:

## Q: what is the best pizza in Chicago
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.47 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: best pizza office in Chicago
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.57 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: best pizza in Texas
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.50 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: cheap office space in Manhattan
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.55 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: how do I bake sourdough bread
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.43 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: tomorrow's weather forecast
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.45 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: predict the price of bitcoin next year
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.58 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.

## Q: family offices headquartered on the moon
- expected: ABSTAIN · got: ABSTAIN · ✓ · mode=abstain · best match similarity 0.63 is below the 0.68 threshold
- I don't have enough verified information to answer that from this dataset. This service only answers from a validated set of family-office records; try naming a family-office type (single- or multi-family), a US state, an investing focus, or a firm name.
