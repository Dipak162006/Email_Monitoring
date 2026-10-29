import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CampaignReviewStep } from "../CampaignReviewStep";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CampaignStepWritePayload } from "../../../types/campaign";

const mockSender: AuthorizedEmailAccount = {
  id: 1,
  company_id: 1,
  name: "Alex Vance",
  email_address: "sales@pulsemail.app",
  provider: "GOOGLE",
  is_active: true,
  is_sync_enabled: true,
};

describe("M4.1 — Fix Campaign Review Email Content Preview", () => {
  it("renders initial email with rich HTML formatting, headings, lists, links, and literal merge tags", () => {
    const initialHtml = `
      <h2>Discover Our Newest Product!</h2>
      <p>Hello {{first_name}}, upgrade your routine with high quality gear.</p>
      <ul>
        <li><strong>Feature A:</strong> Fast sync</li>
        <li><strong>Feature B:</strong> Reliable dispatch</li>
      </ul>
      <p>Visit <a href="https://example.com" target="_blank">our website</a> for more details.</p>
    `;

    render(
      <CampaignReviewStep
        name="Product Launch"
        subject="Exclusive Announcement for {{company_name}}"
        bodyHtml={initialHtml}
        selectedSender={mockSender}
        onEditStep={vi.fn()}
      />
    );

    const snippet = document.getElementById("review-content-snippet");
    expect(snippet).not.toBeNull();

    // Check heading
    const heading = snippet?.querySelector("h2");
    expect(heading).not.toBeNull();
    expect(heading?.textContent).toBe("Discover Our Newest Product!");

    // Check merge tags remain literal and visible
    expect(snippet?.textContent).toContain("Hello {{first_name}}");
    expect(screen.getAllByText(/Exclusive Announcement for {{company_name}}/i).length).toBe(2);

    // Check list and bold tags
    const listItems = snippet?.querySelectorAll("li");
    expect(listItems?.length).toBe(2);
    expect(snippet?.querySelector("strong")?.textContent).toBe("Feature A:");

    // Check link tag and target attribute
    const link = snippet?.querySelector("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("https://example.com");
    expect(link?.getAttribute("target")).toBe("_blank");

    // Check preview classes: scrollable, min height, max height, preview canvas
    expect(snippet?.className).toContain("max-h-72");
    expect(snippet?.className).toContain("overflow-y-auto");
    expect(snippet?.className).toContain("pulsemail-preview-canvas");
  });

  it("renders follow-up emails as formatted HTML previews without flattening or tag stripping", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Re: Quick bump for {{first_name}}",
        body_html: `
          <p>Hi {{first_name}},</p>
          <p>Our engineering team published a <strong>deep-dive</strong> on high throughput architecture.</p>
          <ol>
            <li>50k events/sec with zero jitter</li>
            <li>Direct integration with {{company_name}} systems</li>
          </ol>
        `,
        target_tags: ["enterprise", "lead"],
      },
    ];

    render(
      <CampaignReviewStep
        name="Architecture Outreach"
        subject="Architecture Breakdown"
        bodyHtml="<p>Initial outreach message</p>"
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onEditStep={vi.fn()}
      />
    );

    // Follow-up header and metadata
    expect(screen.getByText("Follow-Up #1 (Step 2)")).toBeDefined();
    expect(screen.getByText(/Waits 2 days if no reply/i)).toBeDefined();
    expect(screen.getByText(/Re: Quick bump for {{first_name}}/i)).toBeDefined();
    expect(screen.getByText("#enterprise")).toBeDefined();
    expect(screen.getByText("#lead")).toBeDefined();
    expect(screen.getByText("(OR matching)")).toBeDefined();
    expect(screen.getByText("Threaded in same conversation")).toBeDefined();

    // Verify HTML preview container contains rendered HTML elements rather than flat text
    const strongEl = screen.getByText("deep-dive");
    expect(strongEl.tagName.toLowerCase()).toBe("strong");

    const olEl = document.querySelector("ol");
    expect(olEl).not.toBeNull();
    expect(olEl?.querySelectorAll("li").length).toBe(2);

    // Merge tags are preserved literally inside the follow-up body
    expect(screen.getByText(/Hi {{first_name}},/i)).toBeDefined();
    expect(screen.getByText(/Direct integration with {{company_name}} systems/i)).toBeDefined();
  });

  it("gracefully falls back to body_text with whitespace-pre-wrap when follow-up has no HTML", () => {
    const plainTextBody = "Line 1: Following up on previous email.\n\nLine 2: Would love to chat tomorrow.\n\nBest regards,\nAlex";

    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 24,
        subject: "Checking in",
        body_text: plainTextBody,
      },
    ];

    render(
      <CampaignReviewStep
        name="Check-in Campaign"
        subject="Initial Check"
        bodyHtml="<p>Initial email</p>"
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onEditStep={vi.fn()}
      />
    );

    expect(screen.getByText(/Line 1: Following up on previous email/)).toBeDefined();
    const plainTextEl = screen.getByText(/Line 1: Following up on previous email/);
    expect(plainTextEl.className).toContain("whitespace-pre-wrap");
    expect(plainTextEl.className).toContain("font-sans");
  });

  it("sanitizes malicious script tags and event handlers using DOMPurify", () => {
    const maliciousHtml = `
      <p>Safe content</p>
      <script>window.__xss_executed = true;</script>
      <img src="x" onerror="alert(1)" />
    `;

    render(
      <CampaignReviewStep
        name="Security Test"
        subject="Safe Email"
        bodyHtml={maliciousHtml}
        selectedSender={mockSender}
        onEditStep={vi.fn()}
      />
    );

    const snippet = document.getElementById("review-content-snippet");
    expect(snippet?.querySelector("script")).toBeNull();
    const img = snippet?.querySelector("img");
    expect(img?.getAttribute("onerror")).toBeNull();
  });

  it("displays fallback 'No content provided.' when both body_html and body_text are empty", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 72,
        subject: "Empty follow up",
        body_html: "",
        body_text: "",
      },
    ];

    render(
      <CampaignReviewStep
        name="Empty Test"
        subject="Empty Subject"
        bodyHtml=""
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onEditStep={vi.fn()}
      />
    );

    const fallbackElements = screen.getAllByText("No content provided.");
    // 1 in initial outreach, 1 in follow-up step
    expect(fallbackElements.length).toBe(2);
  });
});
