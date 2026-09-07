# Tenant 2 interview script

The words the clinic owner provides during onboarding (Surface 2), one answer
per stage, in beat order (see `app/onboarding/beats.py`). This file is the
single source of truth for the proof run: `seed_tenant2_dental.py` parses the
fenced block under each `## stage: <name>` heading and folds it into the lean
v3 profile it pre-populates before calling the confirm endpoint. Every answer
here is free text an owner would actually type.

Nothing here is platform configuration. It is what a dentist would say if
asked the same questions across a counter - which is the whole point of the
generalization proof. If the platform needs anything dental-specific that is
not expressible in these answers plus the three uploaded documents, that is a
domain-agnostic bug in the platform, not a gap in this script.

Note the fee list lives in `services-and-fees.md`, uploaded as a `price_list`
document, not in this script. O-1 onboarding captures what the business is,
not what it charges: a figure may only be stated when it appears in the
owner's own uploaded material (I1 / C-1).

## stage: owner_display_name

```
Priya Raman
```

## stage: business_name

```
Northgate Family Dental
```

## stage: business_type

```
A three-chair general dental practice on a suburban high street. We look
after families - kids from their first tooth, their parents, and a lot of
older patients who've been with us for years.
```

## stage: headcount

```
Three dentists including me, two hygienists, and three front-desk and nursing
staff.
```

## stage: hours

```
Mon-Fri 8:00 to 18:00, Sat 9:00 to 13:00
```

## stage: services

```
Mostly routine check-ups, hygiene and fillings, with crowns, root canals,
extractions and implants when people need them. We also do whitening,
night guards, dentures and bridges.
```

## stage: contact

```
Phone 03 5555 0142, or through the website contact form. Reception picks up
during opening hours.
```

## stage: knowledge_prompt

```
Yes, ready to confirm. I'll upload our policy sheet, the fee list and our
FAQ next.
```
