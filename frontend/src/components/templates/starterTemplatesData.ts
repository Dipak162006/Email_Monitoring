export interface StarterTemplate {
  id: string;
  name: string;
  category: "Onboarding" | "Marketing" | "Newsletter" | "Promotional" | "Transactional";
  description: string;
  iconName: string;
  subject: string;
  bodyHtml: string;
}

export const STARTER_TEMPLATES: StarterTemplate[] = [
  {
    id: "welcome_onboarding",
    name: "Customer Welcome & Onboarding",
    category: "Onboarding",
    description: "Engaging welcome email with personalized greeting, 3-step getting started guide, and quick login CTA.",
    iconName: "Sparkles",
    subject: "Welcome to {{company_name}}, {{customer_name}}! Let's get started",
    bodyHtml: `<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0;">
  <!-- Header Banner -->
  <div style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 36px 28px; text-align: center; color: #ffffff;">
    <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; opacity: 0.9;">GETTING STARTED</p>
    <h1 style="margin: 0; font-size: 26px; font-weight: 800; line-height: 1.3;">Welcome to {{company_name}}!</h1>
  </div>

  <!-- Body Content -->
  <div style="padding: 32px 28px;">
    <p style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #334155;">Hi <strong>{{customer_name}}</strong>,</p>
    <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #475569;">
      We're thrilled to have you with us! Your account is ready, and you now have full access to all features on <strong>{{company_name}}</strong>.
    </p>

    <!-- 3-Step Guide Card -->
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px 24px; margin-bottom: 28px;">
      <h3 style="margin: 0 0 16px 0; font-size: 15px; font-weight: 700; color: #0f172a;">3 Quick Steps to Get the Most Out of Your Account:</h3>
      
      <!-- Step 1 -->
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 14px;">
        <tr>
          <td width="36" valign="top" style="vertical-align: top;">
            <span style="display: inline-block; width: 24px; height: 24px; background-color: #4f46e5; color: #ffffff; border-radius: 50%; text-align: center; line-height: 24px; font-size: 12px; font-weight: 700;">1</span>
          </td>
          <td valign="top" style="vertical-align: top;">
            <strong style="font-size: 14px; color: #0f172a;">Complete your profile</strong>
            <p style="margin: 2px 0 0 0; font-size: 13px; color: #64748b;">Add your team details and configure mailbox notifications.</p>
          </td>
        </tr>
      </table>

      <!-- Step 2 -->
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 14px;">
        <tr>
          <td width="36" valign="top" style="vertical-align: top;">
            <span style="display: inline-block; width: 24px; height: 24px; background-color: #4f46e5; color: #ffffff; border-radius: 50%; text-align: center; line-height: 24px; font-size: 12px; font-weight: 700;">2</span>
          </td>
          <td valign="top" style="vertical-align: top;">
            <strong style="font-size: 14px; color: #0f172a;">Connect your custom domain</strong>
            <p style="margin: 2px 0 0 0; font-size: 13px; color: #64748b;">Verify SPF, DKIM, and DMARC for 99%+ inbox deliverability.</p>
          </td>
        </tr>
      </table>

      <!-- Step 3 -->
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="36" valign="top" style="vertical-align: top;">
            <span style="display: inline-block; width: 24px; height: 24px; background-color: #4f46e5; color: #ffffff; border-radius: 50%; text-align: center; line-height: 24px; font-size: 12px; font-weight: 700;">3</span>
          </td>
          <td valign="top" style="vertical-align: top;">
            <strong style="font-size: 14px; color: #0f172a;">Launch your first campaign</strong>
            <p style="margin: 2px 0 0 0; font-size: 13px; color: #64748b;">Import your contact list and dispatch personalized messages.</p>
          </td>
        </tr>
      </table>
    </div>

    <!-- CTA Button -->
    <div style="text-align: center; margin: 32px 0;">
      <a href="{{login_url}}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #4f46e5; color: #ffffff; font-size: 15px; font-weight: 600; text-decoration: none; padding: 14px 36px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2);">
        Log in to Your Dashboard &rarr;
      </a>
    </div>

    <!-- Help Box -->
    <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 0 8px 8px 0; padding: 14px 18px; margin-top: 24px;">
      <p style="margin: 0; font-size: 13px; color: #1e40af; line-height: 1.5;">
        <strong>Need help?</strong> Reply directly to this email or visit our Help Center at any time. Our support team is always here for you.
      </p>
    </div>
  </div>

  <!-- Footer -->
  <div style="padding: 24px 28px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.6;">
    <p style="margin: 0 0 6px 0;">Sent by <strong>{{company_name}}</strong> &bull; PulseMail Engine</p>
    <p style="margin: 0;"><a href="{{unsubscribe_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Unsubscribe</a> &bull; <a href="{{login_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Manage Preferences</a></p>
  </div>
</div>`,
  },
  {
    id: "product_announcement",
    name: "Product Feature Announcement",
    category: "Marketing",
    description: "Modern announcement email showcasing major updates with a 2-column feature breakdown and interactive CTA.",
    iconName: "Megaphone",
    subject: "Introducing new capabilities in {{company_name}} 🚀",
    bodyHtml: `<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0;">
  <!-- Header -->
  <div style="padding: 32px 28px 24px 28px; text-align: center; background-color: #0f172a; color: #ffffff;">
    <span style="display: inline-block; background-color: #3b82f6; color: #ffffff; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px;">NEW RELEASE</span>
    <h1 style="margin: 0 0 10px 0; font-size: 26px; font-weight: 800; line-height: 1.3;">Smarter Campaigns, Real-Time Insights</h1>
    <p style="margin: 0; font-size: 15px; color: #94a3b8; line-height: 1.5; max-width: 460px; margin-left: auto; margin-right: auto;">
      We've upgraded {{company_name}} with high-speed automated pacing, deliverability protection, and unified telemetry.
    </p>
  </div>

  <!-- Content -->
  <div style="padding: 32px 28px;">
    <p style="margin: 0 0 20px 0; font-size: 15px; line-height: 1.6; color: #334155;">
      Hi {{customer_name}}, here are the biggest highlights designed to give you complete visibility over your emails:
    </p>

    <!-- 2-Column Feature Cards -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 24px;">
      <tr>
        <td width="48%" valign="top" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px;">
          <div style="font-size: 20px; margin-bottom: 8px;">⚡</div>
          <h3 style="margin: 0 0 6px 0; font-size: 15px; font-weight: 700; color: #0f172a;">Configurable Sending Interval</h3>
          <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.5;">Pace outgoing messages with custom delays to maintain domain health and reputation.</p>
        </td>
        <td width="4%"></td>
        <td width="48%" valign="top" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px;">
          <div style="font-size: 20px; margin-bottom: 8px;">📊</div>
          <h3 style="margin: 0 0 6px 0; font-size: 15px; font-weight: 700; color: #0f172a;">Live Telemetry & Ingestion</h3>
          <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.5;">Sub-second delivery status, bounce detection, and open-rate analytics in real-time.</p>
        </td>
      </tr>
    </table>

    <!-- Call to Action -->
    <div style="text-align: center; margin: 32px 0 16px 0;">
      <a href="{{login_url}}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #0f172a; color: #ffffff; font-size: 15px; font-weight: 600; text-decoration: none; padding: 14px 36px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.2);">
        Explore the New Features &rarr;
      </a>
    </div>
  </div>

  <!-- Footer -->
  <div style="padding: 24px 28px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.6;">
    <p style="margin: 0 0 6px 0;">Sent by <strong>{{company_name}}</strong></p>
    <p style="margin: 0;"><a href="{{unsubscribe_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Unsubscribe</a> &bull; <a href="{{login_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Preferences</a></p>
  </div>
</div>`,
  },
  {
    id: "weekly_newsletter",
    name: "Weekly Digest & Newsletter",
    category: "Newsletter",
    description: "Editorial newsletter template featuring lead story, curated articles, and community insights.",
    iconName: "Newspaper",
    subject: "{{company_name}} Weekly Digest: Top stories & performance insights",
    bodyHtml: `<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0;">
  <!-- Masthead -->
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-bottom: 2px solid #0f172a;">
    <tr>
      <td style="padding: 28px 0 16px 28px;" align="left" valign="baseline">
        <h1 style="margin: 0; font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px;">{{company_name}} DISPATCH</h1>
      </td>
      <td style="padding: 28px 28px 16px 0;" align="right" valign="baseline">
        <span style="font-size: 12px; color: #64748b; font-weight: 500;">WEEKLY EDITION</span>
      </td>
    </tr>
  </table>

  <!-- Content -->
  <div style="padding: 28px;">
    <!-- Lead Story -->
    <div style="margin-bottom: 28px; padding-bottom: 24px; border-bottom: 1px solid #e2e8f0;">
      <span style="display: inline-block; background-color: #f1f5f9; color: #475569; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; margin-bottom: 10px;">FEATURED READ</span>
      <h2 style="margin: 0 0 10px 0; font-size: 20px; font-weight: 700; color: #0f172a; line-height: 1.3;">
        Mastering Email Deliverability in 2026: What Top Senders Do Differently
      </h2>
      <p style="margin: 0 0 14px 0; font-size: 14px; color: #475569; line-height: 1.6;">
        From authenticating multi-tenant domains to smart pacing algorithms, explore the technical safeguards that ensure 99%+ of messages hit the primary inbox.
      </p>
      <a href="{{login_url}}" target="_blank" style="color: #4f46e5; font-size: 13px; font-weight: 600; text-decoration: none;">Read full analysis &rarr;</a>
    </div>

    <!-- Secondary Articles List -->
    <div style="margin-bottom: 24px;">
      <h3 style="margin: 0 0 14px 0; font-size: 14px; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px;">THIS WEEK'S HIGHLIGHTS</h3>
      
      <div style="margin-bottom: 14px;">
        <h4 style="margin: 0 0 4px 0; font-size: 15px; font-weight: 600; color: #0f172a;">
          <a href="{{login_url}}" target="_blank" style="color: #0f172a; text-decoration: none;">&bull; Best practices for warming up dedicated IP addresses</a>
        </h4>
        <p style="margin: 0; font-size: 13px; color: #64748b;">Step-by-step guidance on volume scaling schedules.</p>
      </div>

      <div>
        <h4 style="margin: 0 0 4px 0; font-size: 15px; font-weight: 600; color: #0f172a;">
          <a href="{{login_url}}" target="_blank" style="color: #0f172a; text-decoration: none;">&bull; RFC 8058 One-Click Unsubscribe compliance breakdown</a>
        </h4>
        <p style="margin: 0; font-size: 13px; color: #64748b;">How headers protect your reputation with Yahoo and Google.</p>
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div style="padding: 24px 28px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.6;">
    <p style="margin: 0 0 6px 0;">Curated for {{customer_name}} ({{customer_email}})</p>
    <p style="margin: 0;"><a href="{{unsubscribe_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Unsubscribe from Weekly Digest</a></p>
  </div>
</div>`,
  },
  {
    id: "promotional_offer",
    name: "Special Offer & Upgrade",
    category: "Promotional",
    description: "High-converting promo template with promo badge, discount code box, and urgency button.",
    iconName: "Tag",
    subject: "Special Offer for {{customer_name}}: Upgrade today & save 20%",
    bodyHtml: `<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0;">
  <!-- Top Accent Bar -->
  <div style="height: 6px; background: linear-gradient(90deg, #ec4899 0%, #8b5cf6 100%);"></div>

  <!-- Content -->
  <div style="padding: 36px 28px; text-align: center;">
    <span style="display: inline-block; background-color: #fdf2f8; color: #db2777; border: 1px solid #fbcfe8; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 20px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 14px;">EXCLUSIVE UPGRADE OFFER</span>
    
    <h1 style="margin: 0 0 12px 0; font-size: 28px; font-weight: 800; color: #0f172a; line-height: 1.25;">
      Unlock Unlimited Sending at 20% Off
    </h1>
    
    <p style="margin: 0 0 28px 0; font-size: 15px; color: #475569; line-height: 1.6; max-width: 460px; margin-left: auto; margin-right: auto;">
      Hi {{customer_name}}, for the next 48 hours, upgrade your {{company_name}} account to Pro and unlock high-throughput dispatchers, custom tracking domains, and dedicated IP pools.
    </p>

    <!-- Coupon Code Box -->
    <div style="background-color: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 10px; padding: 16px 24px; max-width: 320px; margin: 0 auto 28px auto;">
      <span style="display: block; font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 4px;">YOUR COUPON CODE</span>
      <span style="font-family: ui-monospace, monospace; font-size: 20px; font-weight: 700; color: #4f46e5; letter-spacing: 2px;">PROMO20</span>
    </div>

    <!-- CTA Button -->
    <div style="margin-bottom: 24px;">
      <a href="{{login_url}}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color: #ffffff; font-size: 16px; font-weight: 700; text-decoration: none; padding: 15px 40px; border-radius: 8px; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);">
        Claim Your 20% Discount &rarr;
      </a>
    </div>

    <p style="margin: 0; font-size: 12px; color: #94a3b8;">
      Offer valid until midnight. Automatically applied at checkout when using {{customer_email}}.
    </p>
  </div>

  <!-- Footer -->
  <div style="padding: 24px 28px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.6;">
    <p style="margin: 0 0 6px 0;">Sent by <strong>{{company_name}}</strong></p>
    <p style="margin: 0;"><a href="{{unsubscribe_url}}" target="_blank" style="color: #64748b; text-decoration: underline;">Unsubscribe from promotional emails</a></p>
  </div>
</div>`,
  },
  {
    id: "transactional_receipt",
    name: "Order Confirmation & Receipt",
    category: "Transactional",
    description: "Professional transactional invoice email with itemized table, billing metadata, and tracking link.",
    iconName: "Receipt",
    subject: "Order Confirmation #{{ticket_id}} from {{company_name}}",
    bodyHtml: `<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0;">
  <!-- Header -->
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-bottom: 1px solid #e2e8f0;">
    <tr>
      <td style="padding: 28px 0 28px 28px;" align="left" valign="middle">
        <h2 style="margin: 0; font-size: 20px; font-weight: 800; color: #0f172a;">{{company_name}}</h2>
        <p style="margin: 4px 0 0 0; font-size: 12px; color: #64748b;">Invoice & Receipt</p>
      </td>
      <td style="padding: 28px 28px 28px 0;" align="right" valign="middle">
        <span style="display: inline-block; background-color: #ecfdf5; color: #059669; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px;">PAID</span>
        <p style="margin: 4px 0 0 0; font-size: 12px; font-family: monospace; color: #64748b;">#{{ticket_id}}</p>
      </td>
    </tr>
  </table>

  <!-- Content -->
  <div style="padding: 28px;">
    <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155;">
      Hi {{customer_name}}, thank you for your order! Here is the summary of your transaction:
    </p>

    <!-- Itemized Table -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px;">
      <thead>
        <tr style="border-bottom: 2px solid #e2e8f0; text-align: left; font-size: 12px; color: #64748b; text-transform: uppercase;">
          <th style="padding: 10px 0;">Item Description</th>
          <th style="padding: 10px 0; text-align: center;">Qty</th>
          <th style="padding: 10px 0; text-align: right;">Amount</th>
        </tr>
      </thead>
      <tbody>
        <tr style="border-bottom: 1px solid #f1f5f9; font-size: 14px;">
          <td style="padding: 12px 0; color: #0f172a;"><strong>PulseMail Enterprise Plan</strong><br/><span style="font-size: 12px; color: #64748b;">Monthly Subscription &bull; Auto-renewal</span></td>
          <td style="padding: 12px 0; text-align: center; color: #64748b;">1</td>
          <td style="padding: 12px 0; text-align: right; font-weight: 600; color: #0f172a;">$99.00</td>
        </tr>
        <tr style="border-bottom: 2px solid #e2e8f0; font-size: 14px;">
          <td style="padding: 12px 0; color: #0f172a;"><strong>Dedicated IP Pool Add-on</strong><br/><span style="font-size: 12px; color: #64748b;">Warm reputation allocation</span></td>
          <td style="padding: 12px 0; text-align: center; color: #64748b;">1</td>
          <td style="padding: 12px 0; text-align: right; font-weight: 600; color: #0f172a;">$29.00</td>
        </tr>
        <tr>
          <td colspan="2" style="padding: 16px 0 0 0; font-size: 15px; font-weight: 700; color: #0f172a; text-align: right;">Total Paid:</td>
          <td style="padding: 16px 0 0 0; font-size: 17px; font-weight: 800; color: #4f46e5; text-align: right;">$128.00</td>
        </tr>
      </tbody>
    </table>

    <!-- Action Link -->
    <div style="text-align: center; margin: 28px 0;">
      <a href="{{login_url}}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #0f172a; color: #ffffff; font-size: 14px; font-weight: 600; text-decoration: none; padding: 12px 28px; border-radius: 8px;">
        View Invoice in Account &rarr;
      </a>
    </div>
  </div>

  <!-- Footer -->
  <div style="padding: 24px 28px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.6;">
    <p style="margin: 0 0 4px 0;">Billed to: <strong>{{customer_email}}</strong></p>
    <p style="margin: 0;">Need billing support? Contact <a href="mailto:billing@pulsemail.io" style="color: #64748b; text-decoration: underline;">billing@pulsemail.io</a></p>
  </div>
</div>`,
  },
];
