/**
 * Utilities for parsing email recipient addresses and calculating Reply All distributions.
 */

/**
 * Extract clean, bare email address from an RFC 5322 formatted address string.
 * e.g. "John Doe <john@example.com>" -> "john@example.com"
 *      "<john@example.com>" -> "john@example.com"
 *      "john@example.com" -> "john@example.com"
 */
export function extractEmailAddress(raw: string | null | undefined): string {
  if (!raw) return "";
  const match = raw.match(/<([^>]+)>/);
  if (match && match[1]) {
    return match[1].trim();
  }
  return raw.trim().replace(/^["']|["']$/g, "");
}

export interface ReplyAllRecipients {
  to: string[];
  cc: string[];
}

/**
 * Calculate deduplicated To and Cc recipient lists for Reply All.
 *
 * Rules:
 * 1. If the current user's sending account was the original sender (or OUTGOING):
 *    - To: Original To recipients (excluding sending account)
 *    - Cc: Original Cc recipients (excluding sending account)
 * 2. Otherwise:
 *    - To: Original sender + Original To recipients (excluding sending account)
 *    - Cc: Original Cc recipients (excluding sending account)
 * 3. Exclude sending account from both lists (case-insensitive).
 * 4. Deduplicate addresses case-insensitively.
 * 5. If an address is present in To, it must not be present in Cc.
 */
export function calculateReplyAllRecipients(
  sourceEmail: {
    sender: string;
    recipients: string[];
    cc?: string[] | null;
    direction?: string;
  },
  currentAccountEmail: string
): ReplyAllRecipients {
  const myEmail = extractEmailAddress(currentAccountEmail).toLowerCase();
  const sourceSenderClean = extractEmailAddress(sourceEmail.sender).toLowerCase();

  const isCurrentUserSender =
    (Boolean(myEmail) && sourceSenderClean === myEmail) ||
    sourceEmail.direction === "OUTGOING";

  let rawTo: string[];
  let rawCc: string[];

  if (isCurrentUserSender) {
    rawTo = sourceEmail.recipients || [];
    rawCc = sourceEmail.cc || [];
  } else {
    rawTo = [sourceEmail.sender, ...(sourceEmail.recipients || [])];
    rawCc = sourceEmail.cc || [];
  }

  const toList: string[] = [];
  const seenLower = new Set<string>();

  for (const item of rawTo) {
    const clean = extractEmailAddress(item);
    if (!clean) continue;
    const lower = clean.toLowerCase();
    if (myEmail && lower === myEmail) continue;
    if (!seenLower.has(lower)) {
      seenLower.add(lower);
      toList.push(clean);
    }
  }

  const ccList: string[] = [];
  for (const item of rawCc) {
    const clean = extractEmailAddress(item);
    if (!clean) continue;
    const lower = clean.toLowerCase();
    if (myEmail && lower === myEmail) continue;
    if (!seenLower.has(lower)) {
      seenLower.add(lower);
      ccList.push(clean);
    }
  }

  return { to: toList, cc: ccList };
}
