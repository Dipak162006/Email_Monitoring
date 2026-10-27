import { describe, it, expect } from "vitest";
import {
  extractEmailAddress,
  calculateReplyAllRecipients,
} from "../emailRecipients";

describe("emailRecipients - Address Extraction & Reply All Calculations", () => {
  describe("extractEmailAddress", () => {
    it("extracts bare email from RFC 5322 display-name format", () => {
      expect(extractEmailAddress("John Doe <john.doe@example.com>")).toBe("john.doe@example.com");
      expect(extractEmailAddress("\"Alice Smith\" <alice@acme.org>")).toBe("alice@acme.org");
      expect(extractEmailAddress("<support@service.io>")).toBe("support@service.io");
    });

    it("handles bare email address without brackets", () => {
      expect(extractEmailAddress("user@domain.com")).toBe("user@domain.com");
      expect(extractEmailAddress("  user@domain.com  ")).toBe("user@domain.com");
    });

    it("handles null, undefined, and empty string safely", () => {
      expect(extractEmailAddress(null)).toBe("");
      expect(extractEmailAddress(undefined)).toBe("");
      expect(extractEmailAddress("")).toBe("");
    });
  });

  describe("calculateReplyAllRecipients", () => {
    it("partitions To and Cc correctly when responding to an incoming email", () => {
      const source = {
        sender: "Alice <alice@partner.com>",
        recipients: ["Bob <bob@mycorp.com>", "Charlie <charlie@partner.com>"],
        cc: ["Dave <dave@partner.com>", "Eve <eve@partner.com>"],
        direction: "INCOMING",
      };
      // Bob is the current user's sending account
      const result = calculateReplyAllRecipients(source, "bob@mycorp.com");

      // To should include original sender + other original To recipients, excluding bob
      expect(result.to).toEqual(["alice@partner.com", "charlie@partner.com"]);
      // Cc should preserve original Cc recipients, excluding bob
      expect(result.cc).toEqual(["dave@partner.com", "eve@partner.com"]);
    });

    it("uses original To and Cc without adding sender to To when current user was original sender", () => {
      const source = {
        sender: "Bob <bob@mycorp.com>",
        recipients: ["Alice <alice@partner.com>", "Charlie <charlie@partner.com>"],
        cc: ["Dave <dave@partner.com>"],
        direction: "OUTGOING",
      };
      // Bob is the current account
      const result = calculateReplyAllRecipients(source, "bob@mycorp.com");

      expect(result.to).toEqual(["alice@partner.com", "charlie@partner.com"]);
      expect(result.cc).toEqual(["dave@partner.com"]);
    });

    it("excludes the current sending account case-insensitively from both To and Cc", () => {
      const source = {
        sender: "Alice <alice@example.com>",
        recipients: ["MYACCOUNT@example.com", "colleague@example.com"],
        cc: ["MyAccount@Example.com", "manager@example.com"],
        direction: "INCOMING",
      };
      const result = calculateReplyAllRecipients(source, "myaccount@example.com");

      expect(result.to).toEqual(["alice@example.com", "colleague@example.com"]);
      expect(result.cc).toEqual(["manager@example.com"]);
    });

    it("deduplicates addresses case-insensitively and prevents any address in To from appearing in Cc", () => {
      const source = {
        sender: "Alice <alice@example.com>",
        recipients: [
          "Bob <bob@example.com>",
          "alice@example.com", // duplicate of sender
          "BOB@EXAMPLE.COM",   // duplicate of bob
        ],
        cc: [
          "bob@example.com",     // already in To
          "Alice <ALICE@EXAMPLE.COM>", // already in To
          "David <david@example.com>",
          "david@example.com",   // duplicate in Cc
        ],
        direction: "INCOMING",
      };
      const result = calculateReplyAllRecipients(source, "other@example.com");

      expect(result.to).toEqual(["alice@example.com", "bob@example.com"]);
      expect(result.cc).toEqual(["david@example.com"]);
    });

    it("handles empty or missing cc gracefully", () => {
      const source = {
        sender: "sender@domain.com",
        recipients: ["recipient@domain.com"],
        cc: null,
      };
      const result = calculateReplyAllRecipients(source, "sender@domain.com");
      expect(result.to).toEqual(["recipient@domain.com"]);
      expect(result.cc).toEqual([]);
    });
  });
});
