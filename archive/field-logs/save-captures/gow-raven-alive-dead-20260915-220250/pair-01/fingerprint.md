# Collectible changed-stream semantic fingerprint

Status: **CHANGED_STREAMS_FINGERPRINTED**

This probe sequence-aligns zlib streams only inside changed aligned save slots. It emits hashes, sizes, ordinals, known checkpoint-field labels, and allowlisted engine-style identifiers. It does not emit arbitrary save bytes and does not infer completion state.

## Summary

- Validated zlib streams: A=1268, B=1349
- Changed aligned slots: 17
- Sequence-aligned changed runs: 1
- Runs containing previous slot-6/index-49 adjacency anchor: 0
- Known story/context identifiers found: BOAT_CONTEXT_CONFIG_NORMAL
- Changed runs with Raven/Odin identifiers: 0
- Runtime generation allowed: **false**

## Changed runs

### Slot 17 run 1 — insert A[0, 0] B[0, 81]

- Previous adjacency anchor: false
- Classification hints: story_behavior_context_lead
- Tokens only A: none
- Tokens only B: BOAT_CONTEXT_CONFIG_NORMAL
- Shared safe tokens: none
- B stream 0: off=22271 compressed=50 decompressed=41 sha256=4c363e6b927c01c44a31f1bbe4f93c84a7d3e92f40f269e3b40d52815c066453 fields=state
- B stream 1: off=23702 compressed=54 decompressed=45 sha256=0ca9084f3e435646e51afaf601cddf53426d9dcc499c4b5ff63a829cdf3a41b8 fields=destroyed
- B stream 2: off=24114 compressed=63 decompressed=54 sha256=38f317694be77b9d309ab0ce398cd27733d92bc78177e8e7cdb19fc190a207ab fields=mapSummaryComplete
- B stream 3: off=24475 compressed=99 decompressed=135 sha256=c5696ba4f19bb9b054cdc3608552cc655c190f0802cb324f94d4cf6ecc019b63 fields=state,mapSummaryComplete
- B stream 4: off=25123 compressed=55 decompressed=46 sha256=5547f1b5762a2d0916bc18fa53773fcc1beed0dfc22c7336942059f3a388cc0a fields=none
- B stream 5: off=25596 compressed=63 decompressed=54 sha256=f9b7c98f12ae98352fe530478c68dbe0a61cfbfce7f6a3509411f512221210b2 fields=mapSummaryComplete
- B stream 6: off=26377 compressed=84 decompressed=104 sha256=98dad855c97e28475d45b254b53069e10ae1e9885eb4c41c20528f54623daa48 fields=mapSummaryComplete
- B stream 7: off=27519 compressed=124 decompressed=216 sha256=6c67ff7b1629d3995713b12017f7e2c1bb07f4dfdcc84a14f6c4dff2b033a268 fields=state
- B stream 8: off=28105 compressed=63 decompressed=54 sha256=57a5d088dc6aa1c0f23a5c28480fdb9ed7da904ba217e3cb1952d29f7691ecaa fields=mapSummaryComplete
- B stream 9: off=28406 compressed=63 decompressed=54 sha256=9f12b757669f61ded52be824c287d6492e1ab46b46a60ea4944ee6fe54b358e0 fields=mapSummaryComplete
- B stream 10: off=28587 compressed=63 decompressed=54 sha256=fa88f4ff7422e051d85adccba17426bb70dc683b48ff18945091fd48c8603304 fields=mapSummaryComplete
- B stream 11: off=28768 compressed=63 decompressed=54 sha256=2de8777e56e294d17b9c537677040b493f914f6aff67abc1f74b7b4cd16504f5 fields=mapSummaryComplete
- B stream 12: off=29609 compressed=62 decompressed=54 sha256=881a98738799d6e79519ef9b53194dabff7b789b2447537f0ee6a458dd8dd850 fields=mapSummaryComplete
- B stream 13: off=31169 compressed=63 decompressed=54 sha256=bba2313ae98b0ca2ec02d0feff8018e7bc83c3612a4ce7d3ba5cf29a4ac27c37 fields=mapSummaryComplete
- B stream 14: off=32550 compressed=154 decompressed=215 sha256=db942b692765c6b4fe49cf45a9a6d62264456883b07e7af2150304c003d19762 fields=state,mapSummaryComplete,keysUsed,challengeComplete
- B stream 15: off=33059 compressed=60 decompressed=66 sha256=92bc35d39e9a876e3b63f7900cf28a37762d93202ca87705d074f73eca8ef983 fields=state
- B stream 16: off=33503 compressed=54 decompressed=45 sha256=1e363367f657f90e65796b19e029fbbe7923e6fdd469f7316d27ed77b8a1395e fields=destroyed
- B stream 17: off=35055 compressed=63 decompressed=54 sha256=4a1e4e61e4e4e04870a7a42c9eddf964ccde22dbde91d682b35df17256517cac fields=mapSummaryComplete
- B stream 18: off=35416 compressed=63 decompressed=54 sha256=826666eb0f3bb07c3abb2d50356775e6949677a5ef5d84a63be297293cb3e6c5 fields=mapSummaryComplete
- B stream 19: off=35597 compressed=78 decompressed=85 sha256=ed93b5a13abc16c9ceb747372f1bb666b4ae0291db49364ca85441536d5b5a37 fields=state,mapSummaryComplete
- B stream 20: off=35878 compressed=78 decompressed=85 sha256=4a5fde4bd8764c82089b9dff3bf9ebfc9d4f582f40c82a14933c03a7b7d52ae5 fields=state,mapSummaryComplete
- B stream 21: off=36879 compressed=63 decompressed=54 sha256=b4bfc7617aece8ab9575f2cc9cdad69225a82632cc5f75b470dd30d2715b4c79 fields=mapSummaryComplete
- B stream 22: off=37360 compressed=99 decompressed=135 sha256=5f5aa1b27d53f1cdc588d3bca727458817a531d28ff8bfa507a0ad8f4194ce32 fields=state,mapSummaryComplete
- B stream 23: off=38068 compressed=63 decompressed=54 sha256=3d88bc7a6c56e6a1a54be314b716c35046fe6e3dcb39ea6326b6633acfd2b992 fields=mapSummaryComplete
- B stream 24: off=38249 compressed=102 decompressed=114 sha256=6d54a2e7848d5513cb94414e5ff55421c2d760563c37baabb486f2d642754f76 fields=mapSummaryComplete,destroyed
- B stream 25: off=38571 compressed=63 decompressed=54 sha256=cdab9e2c2952c3cbff000db6837371fa13f2df580e6814bb994b3d0f45080270 fields=mapSummaryComplete
- B stream 26: off=38752 compressed=73 decompressed=79 sha256=14c6c18224c80f2e3da78609675f117d535c14af01f25aab810f77e33de51c5d fields=mapSummaryComplete
- B stream 27: off=39203 compressed=96 decompressed=116 sha256=620bb85be8fd0ebf9c778eb06aba0e532ca57c74bec2d2252694512728e7f308 fields=ravenKilled,mapSummaryComplete
- B stream 28: off=39579 compressed=63 decompressed=54 sha256=767990005c7aaaa9a16e2de2330f1b764750eb5da111d4a91537662a4d9d8482 fields=mapSummaryComplete
- B stream 29: off=39940 compressed=54 decompressed=45 sha256=312e6288df65ca1d2cb63a17193d747eb1649b2577b821f378ceccd2cc17e101 fields=destroyed
- B stream 30: off=40112 compressed=54 decompressed=45 sha256=6b11d7e4712e3ac9e0832d1d4a5f6dc3d22dfbf8c089c056fa4607e6dd29685c fields=destroyed
- B stream 31: off=40944 compressed=53 decompressed=44 sha256=4d69e3f7cd7f93d2115f4aa147d3e8a475305dd8bd47213994a7ba05d2e5d5b0 fields=none
- B stream 32: off=41295 compressed=63 decompressed=54 sha256=7d777df179c9dc1e8ce974f7c633c9f346df2017769fc11621b41e24b504179c fields=mapSummaryComplete
- B stream 33: off=42316 compressed=63 decompressed=54 sha256=7e355a3ca73b8efd18a4e32a39b7f34b1519de99e8d4d63ef2910543d0bb296a fields=mapSummaryComplete
- B stream 34: off=43097 compressed=54 decompressed=45 sha256=a9338dc91d349d7d06ff0c73b877a5c3b5b854717b9a63b897f65b8bd4c2b935 fields=destroyed
- B stream 35: off=43269 compressed=63 decompressed=54 sha256=81af5293e9c28e40bb44bd2bb88833e3f288e29705c240716dadbea2367e2313 fields=mapSummaryComplete
- B stream 36: off=44110 compressed=50 decompressed=41 sha256=578b3060db8e53fbe3c41dab8d3495cd5bc343f8189acdaef051f7e5877ecff0 fields=state
- B stream 37: off=46321 compressed=127 decompressed=155 sha256=4f868ac0af713e60937fa68cd9506d5335acca57abf7574c48df6109705d3c98 fields=state,mapSummaryComplete,keysUsed,challengeComplete
- B stream 38: off=47710 compressed=60 decompressed=66 sha256=30d5dde38ef533f42bb13a0a3fdab4bb91284a8f987c03a60b5bcd66233d1bf4 fields=state
- B stream 39: off=50310 compressed=73 decompressed=79 sha256=5b79cc9a6281fd62ef33c763fd0528385233be64e1457f8e220b3a1dc6c398f5 fields=mapSummaryComplete
- B stream 40: off=50821 compressed=84 decompressed=90 sha256=4ea370d70205242786b677d07c217fe222740ec4b1016c87b665842a0a323b78 fields=mapSummaryComplete
- B stream 41: off=51105 compressed=166 decompressed=261 sha256=81ab04a2fc0cda60cc71bc2abfe5f95e5037421db5fa5e996cd5a344fef4638a fields=state,keysUsed,challengeComplete
- B stream 42: off=51569 compressed=166 decompressed=261 sha256=ee186a645cc1036060dc13dff69d8bd1ef3aa367782dcc39aa80ae5b0f39fba0 fields=state,keysUsed,challengeComplete
- B stream 43: off=52101 compressed=60 decompressed=66 sha256=68664d6d0253dc8f544e251ea607355d8550484b6e5e232d6aeb2d8689ba2562 fields=state
- B stream 44: off=52305 compressed=61 decompressed=66 sha256=9af11e5bc2db7043e71df0c25def28d81d9d15d1868fa8858995fc76ee9f9f4e fields=state
- B stream 45: off=52810 compressed=156 decompressed=236 sha256=221fa8b7e79e89a372553887de8724eb7e98de23480f7508f5831c0187a46792 fields=state,keysUsed,challengeComplete
- B stream 46: off=53249 compressed=165 decompressed=261 sha256=c847275633676cdfaa48ea20e4aa57fe35d69875fe8e33a01b112b04d88bafec fields=state,keysUsed,challengeComplete
- B stream 47: off=54140 compressed=61 decompressed=66 sha256=273b4eaa88c30b300b4ed25ebb601f0b610714597bd1699e044cbb45a40ba367 fields=state
- B stream 48: off=54525 compressed=52 decompressed=41 sha256=85adfb9a17c2ab2bd04795457795de4b39dc4365a18240357235036f49324238 fields=state
- B stream 49: off=202972 compressed=1481 decompressed=3194 sha256=6c81cdd17533bd94f07ddd8cee08a4e2d6249e893ae96c6a253a5c8bdb298911 fields=state
- B stream 50: off=221679 compressed=154 decompressed=276 sha256=cbb6c3fae52e12930cd187d8af93687f8e553a66220293bae87c2fe93c45782b fields=none
- B stream 51: off=230326 compressed=205 decompressed=353 sha256=fb41deaa0566ef55872b1224e87815f3b10b6d987217367b49efd7bf432c280b fields=state
- B stream 52: off=240462 compressed=94 decompressed=125 sha256=76aff5f0eb8540f71545766b24c59d781c107c8af998b9f632cd9b931997f228 fields=none
- B stream 53: off=258869 compressed=408 decompressed=757 sha256=58933fc36781436530f8818b55602f467bb8bd4205d3e13bff070b58ecff53df fields=none
- B stream 54: off=260163 compressed=18 decompressed=10 sha256=56592ee14f159def6081ee4babe16bdedcc57573c67c17f1aa4edc9f6d784ca8 fields=none
- B stream 55: off=265232 compressed=217 decompressed=337 sha256=59901340605a19fa1ca0d6dc1fcd169c98ffba5e25aa7ed7b6bb827d2cb70e06 fields=none
- B stream 56: off=512109 compressed=1977 decompressed=4284 sha256=f5070d8a8eab9a9bba5894a1115d0a3d2702022ccad82dc22e525ffc8459aafb fields=state,destroyed,keysUsed,challengeComplete
- B stream 57: off=518828 compressed=522 decompressed=877 sha256=0ff2a0fee495608c1a06aa40ce18489b7d766667a4f08c3c35eb13605b6d625c fields=ravenKilled,state
- B stream 58: off=573790 compressed=964 decompressed=1936 sha256=2dcc34a1f901fd44f7183ad8d771e22633507bdccded870913fae511e56c55dc fields=none
- B stream 59: off=599069 compressed=71 decompressed=76 sha256=a882a4138d71b73cbbde12912f677abe3a88f1e88d39057687e275e57989c9bb fields=none
- B stream 60: off=609957 compressed=928 decompressed=1852 sha256=d6db7e8cbbe17c4117055d48ff4796671356984db97a72bfcf49a99dd4502a8a fields=state,destroyed
- B stream 61: off=687082 compressed=210 decompressed=351 sha256=6c964e14597d84d98625e0188018007ab47a6bc40b1452292cb567713ccbc02a fields=state
- B stream 62: off=744300 compressed=63 decompressed=69 sha256=e442c3415c00a376b69ffb2659b83785d93614dde1180c62af4c7ca655aaa4e2 fields=none
- B stream 63: off=756607 compressed=460 decompressed=831 sha256=74d33756944530f054ad1d5ef4b97221f22ae322833570895f11b0a781998e18 fields=state,destroyed
- B stream 64: off=833858 compressed=365 decompressed=628 sha256=109d5c7a9b29c2673252220c6961f4b4fc1aced3e4735a64e556d7db24036c95 fields=state
- B stream 65: off=898379 compressed=1293 decompressed=2665 sha256=98ca72d531e4e44f6c62786f132c3036cfbdc0ba9141fd8c19c6eca680d3591e fields=state,destroyed
- B stream 66: off=926920 compressed=198 decompressed=286 sha256=8a88e42dc70ed58e8a1f85ad0ed82c2dd8b8a201517efc25cf595fda2f8a4f6b fields=state
- B stream 67: off=928471 compressed=412 decompressed=733 sha256=913cc0f198239d5991f5cb12ca345233a71b8122ef72911170f06910ed09040b fields=state
- B stream 68: off=935684 compressed=887 decompressed=1697 sha256=58ecfaf51276534a732ad43d97107f2f161733b573e83cc18fae4f85ce24fb0a fields=state,destroyed
- B stream 69: off=986455 compressed=381 decompressed=726 sha256=f4fd97afabf9601cfef3cef9085623574415377eaf7bfc55afed11c88ab1e773 fields=none
- B stream 70: off=1001626 compressed=316 decompressed=607 sha256=c35070849ee5463778a8d16d632ce5e5553375e03ae3f64270fb017e76b1a075 fields=state
- B stream 71: off=1025419 compressed=537 decompressed=922 sha256=114ae67fb46dde93bb8b74a72b42beaff1fbb8838043585d95a7bf163a297333 fields=state
- B stream 72: off=1033286 compressed=620 decompressed=1108 sha256=f5bb241b1bb963a9b6f89dca7b684ab4e93a01185ba64c0991afbbd4552c7f29 fields=state
- B stream 73: off=1035475 compressed=53 decompressed=44 sha256=08de3b8af3547ef7407249ef22036636f0c6c00720d79a42d35947d40e5ddc50 fields=none
- B stream 74: off=1125966 compressed=273 decompressed=403 sha256=6c60ee00a8fc65304989febd4f905ed7cbf9db60b836667fa51e8e474e993904 fields=none
- B stream 75: off=1144293 compressed=43 decompressed=35 sha256=83bd9e6fb490e4b9caaa1cad1fa50708f59ed7388e77765dfc77e16cca6a8641 fields=none
- B stream 76: off=1156495 compressed=934 decompressed=1878 sha256=74c1008b434541683b4723a305963e98069f8165764b96f6509e0187953d40b0 fields=state
- B stream 77: off=1182307 compressed=140 decompressed=221 sha256=acfd3ab2d1279a22810262abdc582dc33a567ac39fbf4b0b5a601ac48636ce02 fields=none
- B stream 78: off=1194166 compressed=187 decompressed=244 sha256=50be01370db554fe037a0b318cc493558144c9d24c6e9aa30856af07946826f8 fields=state
- B stream 79: off=1218614 compressed=295 decompressed=569 sha256=aae3b04987c3869b81e038294f01860b211d65d67b5c70bdb15e7d0f983a4a25 fields=none
- B stream 80: off=1298309 compressed=575 decompressed=1035 sha256=f802ed65efecd138823c04ffd5e54373121d822269ad631472814a4809098361 fields=state,keysUsed,challengeComplete

## Target-field proximity to changed streams

- `ravenKilled`: A min=None within4=0/0; B min=0 within4=2/2
- `state`: A min=None within4=0/0; B min=0 within4=37/37
- `mapSummaryComplete`: A min=None within4=0/0; B min=0 within4=29/29
- `bRuneReadStarted`: A min=None within4=0/0; B min=None within4=0/0
- `wellRead`: A min=None within4=0/0; B min=None within4=0/0
- `destroyed`: A min=None within4=0/0; B min=0 within4=11/11
- `keysUsed`: A min=None within4=0/0; B min=0 within4=8/8
- `challengeComplete`: A min=None within4=0/0; B min=0 within4=8/8

## Interpretation

A changed-run token can help determine what a structural save difference belongs to, but it cannot bind a persisted value to an individual collectible. Exact instance binding plus known opposite semantic states for that same object are still required before any state could be used by production runtime code.

Unknown collectible state remains hidden/fail-closed.
