export interface EmailBlockItem {
  id: string;
  title: string;
  category: "Action" | "Layout" | "Content" | "Compliance";
  description: string;
  iconName: string;
  badge?: string;
  html: string;
}

export const EMAIL_BLOCKS: EmailBlockItem[] = [
  {
    id: "cta_button",
    title: "CTA Button",
    category: "Action",
    description: "Centered high-converting call-to-action button with custom link.",
    iconName: "MousePointerClick",
    badge: "Essential",
    html: `<div data-email-block="button" style="text-align: center; margin: 28px 0; padding: 6px 0;">
  <a href="{{login_url}}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #4f46e5; color: #ffffff; font-size: 15px; font-weight: 600; text-decoration: none; padding: 14px 34px; border-radius: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.25);">
    Click Here to Continue &rarr;
  </a>
</div>`,
  },
  {
    id: "hero_header",
    title: "Hero Header",
    category: "Content",
    description: "Prominent header with headline, subtitle, and branded banner.",
    iconName: "Heading",
    badge: "Popular",
    html: `<div data-email-block="hero" style="text-align: center; padding: 32px 24px; background: linear-gradient(135deg, #f8fafc 0%, #edf2f7 100%); border-radius: 12px; margin: 20px 0; border: 1px solid #e2e8f0;">
  <h1 style="margin: 0 0 10px 0; font-size: 26px; font-weight: 800; color: #0f172a; line-height: 1.25; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    Headline Title Goes Here
  </h1>
  <p style="margin: 0; font-size: 15px; color: #475569; line-height: 1.6; max-width: 480px; margin-left: auto; margin-right: auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    Add your compelling subtitle or value proposition here. You can customize text, colors, and formatting easily.
  </p>
</div>`,
  },
  {
    id: "image_banner",
    title: "Image Banner",
    category: "Content",
    description: "Responsive full-width or rounded image banner with caption.",
    iconName: "Image",
    html: `<div data-email-block="image" style="margin: 20px 0; text-align: center;">
  <img src="https://images.unsplash.com/photo-1579546929518-9e396f3cc809?auto=format&fit=crop&w=1200&q=80" alt="Email Banner" style="max-width: 100%; height: auto; border-radius: 10px; display: block; margin: 0 auto; border: 0;" />
  <p style="margin: 6px 0 0 0; font-size: 12px; color: #94a3b8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">Image caption or description goes here.</p>
</div>`,
  },
  {
    id: "two_column_cards",
    title: "2-Column Cards",
    category: "Layout",
    description: "Side-by-side product or feature highlight cards.",
    iconName: "Columns",
    badge: "Grid",
    html: `<div data-email-block="columns" style="margin: 24px 0;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse: collapse;">
    <tr>
      <td width="48%" valign="top" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px;">
        <h3 style="margin: 0 0 8px 0; font-size: 16px; font-weight: 700; color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          ✨ Feature Title 1
        </h3>
        <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          Describe the first benefit, offer, or update in this column with clear and engaging copy.
        </p>
      </td>
      <td width="4%"></td>
      <td width="48%" valign="top" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px;">
        <h3 style="margin: 0 0 8px 0; font-size: 16px; font-weight: 700; color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          🚀 Feature Title 2
        </h3>
        <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          Describe the second benefit or feature in this column. Both columns render cleanly across email clients.
        </p>
      </td>
    </tr>
  </table>
</div>`,
  },
  {
    id: "callout_box",
    title: "Callout / Notice Box",
    category: "Content",
    description: "Highlighted message container for tips, updates, or key notes.",
    iconName: "Info",
    html: `<div data-email-block="callout" style="margin: 20px 0; padding: 16px 20px; background-color: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 0 8px 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <p style="margin: 0; font-size: 14px; color: #1e40af; line-height: 1.5;">
    <strong>💡 Pro Tip:</strong> Insert key reminders, important instructions, or account notifications inside this callout box.
  </p>
</div>`,
  },
  {
    id: "divider_line",
    title: "Divider Line",
    category: "Layout",
    description: "Subtle separator line to divide sections gracefully.",
    iconName: "Minus",
    html: `<div data-email-block="divider" style="margin: 28px 0; border-top: 1px solid #e2e8f0;"></div>`,
  },
  {
    id: "social_links",
    title: "Social Links Bar",
    category: "Action",
    description: "Connected channels bar with Twitter/X, LinkedIn, and GitHub.",
    iconName: "Share2",
    html: `<div data-email-block="social" style="text-align: center; margin: 24px 0; padding: 12px 0;">
  <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 1px; text-transform: uppercase; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">STAY CONNECTED</p>
  <div style="font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <a href="https://twitter.com" target="_blank" style="color: #64748b; text-decoration: none; margin: 0 8px;">Twitter / X</a>
    <span style="color: #cbd5e1;">&bull;</span>
    <a href="https://linkedin.com" target="_blank" style="color: #64748b; text-decoration: none; margin: 0 8px;">LinkedIn</a>
    <span style="color: #cbd5e1;">&bull;</span>
    <a href="https://github.com" target="_blank" style="color: #64748b; text-decoration: none; margin: 0 8px;">GitHub</a>
  </div>
</div>`,
  },
  {
    id: "unsubscribe_footer",
    title: "Unsubscribe Footer",
    category: "Compliance",
    description: "Unsubscribe footer with company info and opt-out link placeholder.",
    iconName: "ShieldCheck",
    badge: "Required",
    html: `<div data-email-block="footer" style="margin-top: 36px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <p style="margin: 0 0 6px 0;">Sent by <strong>{{company_name}}</strong> &bull; PulseMail Engine</p>
  <p style="margin: 0 0 6px 0;">You received this email because you are a registered customer of {{company_name}}.</p>
  <p style="margin: 0;">
    <a href="{{unsubscribe_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Unsubscribe from these emails</a>
    &bull;
    <a href="{{login_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Manage Preferences</a>
  </p>
</div>`,
  },
];
