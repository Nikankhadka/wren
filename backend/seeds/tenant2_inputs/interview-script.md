# Tenant 2 interview script

The exact words the clinic owner types into the onboarding conversation
(Surface 2), one answer per stage, in `STAGE_ORDER` (see
`app/onboarding/flow.py`). This file is the single source of truth for the
proof run: `seed_tenant2_dental.py` parses the fenced block under each
`## stage: <name>` heading and posts it verbatim to
`POST /api/onboarding/message`.

Nothing here is platform configuration. It is what a dentist would say if
asked the same six questions across a counter - which is the whole point of
the generalization proof. If the platform needs anything dental-specific
that is not expressible in these six answers plus the three uploaded
documents, that is a domain-agnostic bug in the platform, not a gap in this
script.

## stage: identity

```
We're Northgate Family Dental, a three-chair general dental practice in a
suburban high street. We look after families - kids from their first tooth,
their parents, and a lot of older patients who've been with us for years.
Mostly routine check-ups, hygiene and fillings, with crowns, root canals,
extractions and implants when people need them.
```

## stage: tone

```
Warm and reassuring, but never chatty for the sake of it. A lot of people
are genuinely anxious about the dentist, so be calm and plain-spoken, explain
things without jargon, and never oversell treatment. Professional, not
stiff.
```

## stage: services

```
New patient exam is 95 dollars and a routine check-up is 55. Bitewing X-rays
35 for the set, panoramic X-ray 90, emergency exam for pain 75. Scale and
polish with the hygienist is 85, deep cleaning is 130 per quadrant. Fluoride
varnish 30, fissure sealant 45 a tooth, night guard 320. White fillings are
145 for a single surface and 195 for larger ones, amalgam 120. Porcelain
crown 950, veneer 890, inlay or onlay 780. Root canals are 620 for a front
tooth, 740 for a premolar, 920 for a molar. Simple extraction 180, surgical
extraction 340, wisdom tooth 420 each. Implant with the crown is 3200, a
three-unit bridge 2400, full denture 1450, partial denture 980. Take-home
whitening 380, in-chair whitening 550, a top-up gel syringe 45.
```

## stage: pricing_rules

```
Yes, a few. Deep cleaning is charged per quadrant, so a full mouth is four
of them. Wisdom teeth are per tooth. Anything booked Saturday morning or a
weekday evening after six has a 60 dollar out-of-hours surcharge on top of
the treatment fee, but not on the emergency slots we keep free each weekday
morning. Missed appointments are 50 dollars after the first one in a year.
The family preventive plan is 55 a month for a household.
```

## stage: pricing_rules.followup

The answer above names two rules (deep cleaning, wisdom teeth) whose prices
the owner had already given in the services answer and did not repeat here.
The flow refuses to store a rule with no amount and asks for them by name;
this is the reply. A `<stage>.followup` block is used only if the flow stays
on that stage.

```
Sorry, yes - deep cleaning is 130 dollars per quadrant, and wisdom teeth are
420 dollars per tooth.
```

## stage: escalation_threshold

```
Be cautious. Anything clinical - whether someone actually needs a
particular treatment, what's causing their pain, whether something is
urgent - goes to a human, always. Same for anything about an individual
patient's records or insurance. Answer fees, opening hours, policies and
general "what is this treatment" questions yourself, but if you're not sure,
hand it over.
```

## stage: knowledge_prompt

```
Yes, ready to confirm. I'll upload our policy sheet, the fee list and our
FAQ next.
```
