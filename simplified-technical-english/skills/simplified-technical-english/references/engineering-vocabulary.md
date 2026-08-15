# Engineering vocabulary — substitutions for software prose

An original substitution table for the words engineers reach for that a rushed or
non-native reader stumbles on. This is **not** the ASD-STE100 approved-word
dictionary (which is ASD copyright and is not redistributable — see
`rules.md`). It is a working list for this marketplace, aimed at the vocabulary
that actually shows up in pull requests, runbooks, and design docs.

`scripts/check_ste.py` parses the tables below, so this file is both documentation
and the checker's data. Keep the marker comments and the three-column shape
intact when you add rows.

The **Level** column controls the checker:

- `error` — fails the check. Unambiguously opaque to a non-native reader, and a
  plain replacement always exists.
- `warn` — advisory. Usually better replaced, but context can justify it.

Matching is case-insensitive and whole-word, and it never looks inside code spans.

---

## Wordy and abstract verbs

<!-- checker:substitutions -->

| Avoid | Use instead | Level |
|---|---|---|
| utilise | use | error |
| utilize | use | error |
| leverage | use | error |
| facilitate | help | error |
| initiate | start | warn |
| terminate | stop | warn |
| commence | start | error |
| endeavour | try | error |
| endeavor | try | error |
| ascertain | find out | error |
| demonstrate | show | warn |
| modify | change | warn |
| implement | build | warn |
| perform | do | warn |
| provide | give | warn |
| require | need | warn |
| attempt | try | warn |
| obtain | get | warn |
| additional | more | warn |
| approximately | about | warn |
| subsequently | then | error |
| prior to | before | error |
| in order to | to | error |
| due to the fact that | because | error |
| in the event that | if | error |
| at this point in time | now | error |
| a number of | some | warn |
| the majority of | most | warn |
| is able to | can | warn |
| has the ability to | can | error |
| it should be noted that | note that | error |

## Phrasal verbs

A phrasal verb means something its two words do not. Non-native readers translate
the parts and get the wrong answer.

<!-- checker:substitutions -->

| Avoid | Use instead | Level |
|---|---|---|
| spin up | start | error |
| stand up | start | error |
| tear down | remove | error |
| roll out | release | error |
| roll back | revert | error |
| back out | revert | error |
| kick off | start | error |
| fire off | send | error |
| bring up | start | error |
| take down | stop | error |
| shut off | stop | warn |
| set up | configure | warn |
| carry out | do | error |
| put in place | add | error |
| come up with | design | error |
| figure out | find | error |
| look into | investigate | error |
| deal with | handle | warn |
| end up | become | error |
| fall over | fail | error |
| blow up | fail | error |
| hold off | wait | error |
| pick up | read | warn |
| reach out to | contact | error |

## Idioms and metaphors

<!-- checker:substitutions -->

| Avoid | Use instead | Level |
|---|---|---|
| low-hanging fruit | easy improvement | error |
| move the needle | change the result | error |
| boil the ocean | do too much at once | error |
| under the hood | internally | error |
| out of the box | by default | error |
| off the shelf | ready-made | error |
| in the weeds | too detailed | error |
| the long tail | the rare cases | error |
| a rabbit hole | a distraction | error |
| bite the bullet | accept the cost | error |
| best of both worlds | both benefits | error |
| silver bullet | complete solution | error |
| happy path | the expected case | error |
| foot-gun | easy mistake | error |
| bake in | include | error |
| smoke test | basic check | warn |
| sanity check | basic check | warn |
| apples to apples | a fair comparison | error |
| on the fly | while running | error |
| north star | main goal | error |
| heavy lifting | the difficult work | error |
| paper over | hide | error |
| ship it | release it | warn |

## Vague nouns

These say nothing on their own. Replace with what the thing actually is.

<!-- checker:substitutions -->

| Avoid | Use instead | Level |
|---|---|---|
| synergy | shared benefit | error |
| solution | name the thing | warn |
| functionality | name the function | warn |
| capability | name what it does | warn |
| stuff | name the items | error |
| things | name the items | warn |

---

## Synonym groups — pick one and keep it

The checker reports **terminology drift** when a document uses more than one word
from the same group. It does not know which one you should pick; it only tells
you that you used two. Choose the one that fits the system, then use it
everywhere.

Each line is one group.

<!-- checker:synonyms -->

- call, invocation, request, hit
- error, failure, fault, exception
- user, customer, client, end user
- delete, remove, drop, purge
- start, launch, boot, initialise, initialize
- stop, halt, terminate, kill
- setting, option, parameter, flag, config
- fetch, retrieve, get, pull
- store, save, persist, write
- check, validate, verify, assert
- job, task, work item, unit of work
- service, server, host, node, instance
- retry, re-attempt, replay
- queue, buffer, backlog

---

## Noun clusters — the pattern, not a word list

The checker flags four or more consecutive content words with no article,
preposition, or conjunction between them. It cannot suggest the fix, because the
fix depends on which noun is the head. The recipe:

1. Find the head noun — the thing the phrase actually *is*. It is usually last.
2. Move it to the front.
3. Reconnect the rest with *of*, *for*, *that*, or a relative clause.

| Cluster | Rewrite |
|---|---|
| user session token refresh handler | the handler that refreshes session tokens |
| database connection pool exhaustion alert | the alert for an exhausted connection pool |
| batch job retry backoff configuration | the backoff settings for batch job retries |
| customer payment method validation failure | a failure to validate the customer's payment method |
| message queue consumer lag threshold | the lag threshold for queue consumers |

Note the rewrites are longer in words and shorter in effort. That is the trade
STE makes everywhere: the word cap is per sentence, not per document.
