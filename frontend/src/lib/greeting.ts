/**
 * W-9 US-8: the customer's first message.
 *
 * The identity line is fixed and always comes first - it is what the assistant
 * is, and a tenant does not get to configure that away. A configured welcome
 * (`config->customer.greeting`) is optional content that follows it, kept only
 * for the part that says something the identity line has not.
 */

/**
 * Words a greeting can add without adding anything: salutation vocabulary, and
 * the function words that carry a sentence without saying anything on their
 * own. A sentence built only from these has told the customer nothing the
 * identity line did not, so it is dropped. A sentence that genuinely adds
 * something always carries at least one word outside this list, which is what
 * keeps the rule from eating real content.
 *
 * The second group is what catches the greeting this app used to compose for
 * itself - "Hi! How can I help you with {business} today?" - which is sitting
 * in the config of every tenant onboarded before this ticket.
 */
const EMPTY_WORDS = [
  "hello",
  "hey",
  "welcome",
  "there",
  "again",
  "and",
  "to",
  "our",
  "us",
  "we",
  "you",
  "your",
  "with",
  "the",
  "a",
  "an",
  "is",
  "are",
  "for",
  "of",
  "at",
  "on",
  "it",
  "here",
];

function words(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

/**
 * The identity line, then whatever the configured greeting adds to it.
 *
 * The greeting is normalized sentence by sentence: a sentence whose every word
 * already appears in the identity line, or is plain salutation vocabulary, is
 * dropped. So "Hi! Welcome to ByteFix. We can quote a repair." keeps only its
 * last sentence, and a greeting that is nothing but another hello disappears
 * entirely rather than greeting the customer twice. Nothing is rewritten - a
 * sentence is kept whole or not at all.
 */
export function customerOpening(displayName: string, greeting: string | null): string {
  const identity = `Hi, I'm ${displayName}'s assistant. How can I help today?`;
  const known = new Set([...words(identity), ...EMPTY_WORDS]);
  const rest = (greeting ?? "")
    .split(/(?<=[.!?])\s+/)
    .filter((sentence) => words(sentence).some((word) => !known.has(word)))
    .join(" ")
    .trim();
  return rest ? `${identity} ${rest}` : identity;
}
