import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RichTextEditor, normalizeImageUrl, cleanPastedHtml } from "../RichTextEditor";

// Mock document.execCommand
document.execCommand = vi.fn();

describe("RichTextEditor Toolbar & Modular Block Controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("URL Normalization & HTML Cleaning Utilities", () => {
    it("normalizeImageUrl extracts target URL from Google Images redirect parameters", () => {
      const googleImgResUrl = "https://www.google.com/imgres?imgurl=https%3A%2F%2Fexample.com%2Fbanner.png&imgrefurl=https%3A%2F%2Fexample.com";
      expect(normalizeImageUrl(googleImgResUrl)).toBe("https://example.com/banner.png");

      const googleUrlParam = "https://images.google.com/url?url=https%3A%2F%2Fexample.com%2Fphoto.jpg";
      expect(normalizeImageUrl(googleUrlParam)).toBe("https://example.com/photo.jpg");

      const plainUrl = "https://example.com/direct.png";
      expect(normalizeImageUrl(plainUrl)).toBe("https://example.com/direct.png");

      const protocolLessUrl = "cdn.example.com/hero.webp";
      expect(normalizeImageUrl(protocolLessUrl)).toBe("https://cdn.example.com/hero.webp");
    });

    it("cleanPastedHtml normalizes wide tables, Gmail offsets, and adds referrerpolicy to images", () => {
      const dirtyHtml = `
        <div class="gmail_quote" style="margin-left: 40px; padding-left: 20px;">
          <table width="750" style="width: 750px;">
            <tbody>
              <tr>
                <td>Pasted Content Cell</td>
              </tr>
            </tbody>
          </table>
          <img src="https://ci3.googleusercontent.com/mail-sig/sample.png" style="width: 800px;" />
        </div>
      `;

      const cleaned = cleanPastedHtml(dirtyHtml);
      expect(cleaned).toContain('referrerpolicy="no-referrer"');
      expect(cleaned).toContain('max-width: 600px');
      expect(cleaned).toContain('border-collapse: collapse');
      expect(cleaned).toContain('margin-left: auto');
      expect(cleaned).toContain('margin-right: auto');
    });
  });

  it("opens Docked Sticky Image Inspector on image click, resizes to 50%, and updates alignment", () => {
    const handleChange = vi.fn();
    const initialHtml = `
      <div data-email-block="image" style="text-align: center;">
        <img src="https://example.com/banner.png" alt="Banner" style="width: 100%; display: block; margin: 0 auto;" />
      </div>
    `;

    render(
      <RichTextEditor
        initialHtml={initialHtml}
        onChange={handleChange}
      />
    );

    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img).toBeTruthy();

    // Click on image
    fireEvent.click(img);

    // Docked inspector region should now be visible at the top
    const inspector = screen.getByRole("region", { name: "Image inspector" });
    expect(inspector).toBeTruthy();
    expect(screen.getByText("Image Selected")).toBeTruthy();
    expect(screen.getByText("Replace")).toBeTruthy();

    const btn50 = screen.getByTitle("50% Width");
    expect(btn50).toBeTruthy();

    // Click 50% width
    fireEvent.click(btn50);
    expect(img.style.width).toBe("50%");
    expect(img.style.maxWidth).toBe("50%");
    expect(img.getAttribute("width")).toBe("280");
    expect(handleChange).toHaveBeenCalled();

    // Alignment in inspector: Click Align Left
    const alignLeftBtns = screen.getAllByTitle("Align Left");
    const dockedAlignLeft = alignLeftBtns[alignLeftBtns.length - 1];
    fireEvent.click(dockedAlignLeft);

    expect(img.style.display).toBe("block");
    expect(img.style.marginLeft).toBe("0px");
    expect(img.style.marginRight).toBe("auto");
    const parentBlock = img.closest('[data-email-block="image"]') as HTMLElement;
    expect(parentBlock.style.textAlign).toBe("left");

    // Click Align Right in inspector
    const alignRightBtns = screen.getAllByTitle("Align Right");
    const dockedAlignRight = alignRightBtns[alignRightBtns.length - 1];
    fireEvent.click(dockedAlignRight);

    expect(img.style.marginLeft).toBe("auto");
    expect(img.style.marginRight).toBe("0px");
    expect(parentBlock.style.textAlign).toBe("right");

    // Close Inspector button
    const closeBtn = screen.getByTitle("Close Inspector");
    fireEvent.click(closeBtn);
    expect(screen.queryByRole("region", { name: "Image inspector" })).toBeNull();
  });

  it("opens Docked Sticky CTA Button Inspector on <a> click and updates text, href, alignment, and color", () => {
    const handleChange = vi.fn();
    const initialHtml = `
      <div data-email-block="button" style="text-align: center;">
        <a href="https://example.com/login" style="display: inline-block; background-color: rgb(79, 70, 229); color: #ffffff; padding: 12px 24px; text-decoration: none;">Log In Now</a>
      </div>
    `;

    render(
      <RichTextEditor
        initialHtml={initialHtml}
        onChange={handleChange}
      />
    );

    const link = screen.getByRole("link", { name: "Log In Now" }) as HTMLAnchorElement;
    expect(link).toBeTruthy();

    // Click on CTA Button link
    fireEvent.click(link);

    // Docked CTA Button inspector should be open
    const inspector = screen.getByRole("region", { name: "Link inspector" });
    expect(inspector).toBeTruthy();
    expect(screen.getByText("CTA Button")).toBeTruthy();

    // Update text
    const textInput = screen.getByPlaceholderText("Button text...");
    fireEvent.change(textInput, { target: { value: "Get Started Now" } });
    expect(link.textContent).toBe("Get Started Now");
    expect(handleChange).toHaveBeenCalled();

    // Update URL
    const urlInput = screen.getByTitle("Hyperlink URL");
    fireEvent.change(urlInput, { target: { value: "https://acme.org/start" } });
    const applyBtn = screen.getByTitle("Apply URL");
    fireEvent.click(applyBtn);
    expect(link.getAttribute("href")).toBe("https://acme.org/start");

    // Update Alignment
    const alignLeftBtns = screen.getAllByTitle("Align Left");
    const dockedAlignLeft = alignLeftBtns[alignLeftBtns.length - 1];
    fireEvent.click(dockedAlignLeft);

    const btnContainer = link.closest('[data-email-block="button"]') as HTMLElement;
    expect(btnContainer.style.textAlign).toBe("left");

    // Update Background Color using presets
    const roseColorBtn = screen.getByTitle("#e11d48");
    fireEvent.click(roseColorBtn);
    expect(link.style.backgroundColor).toBe("rgb(225, 29, 72)");
  });

  it("top toolbar alignment buttons align selected images and modular blocks properly", () => {
    const handleChange = vi.fn();
    const initialHtml = `
      <div data-email-block="hero">
        <p style="text-align: center; max-width: 480px; margin-left: auto; margin-right: auto;">Subtitle text</p>
      </div>
      <div data-email-block="image" style="text-align: center;">
        <img src="https://example.com/pic.jpg" alt="Photo" style="display: block; margin: 0 auto;" />
      </div>
    `;

    render(
      <RichTextEditor
        initialHtml={initialHtml}
        onChange={handleChange}
      />
    );

    const img = screen.getByRole("img") as HTMLImageElement;
    // Select image
    fireEvent.click(img);

    // Use top toolbar align left
    const topToolbarAlignLeft = screen.getByRole("button", { name: "Align left" });
    fireEvent.click(topToolbarAlignLeft);

    expect(img.style.marginLeft).toBe("0px");
    expect(img.style.marginRight).toBe("auto");
    const imgWrapper = img.closest('[data-email-block="image"]') as HTMLElement;
    expect(imgWrapper.style.textAlign).toBe("left");

    // Use top toolbar align right
    const topToolbarAlignRight = screen.getByRole("button", { name: "Align right" });
    fireEvent.click(topToolbarAlignRight);

    expect(img.style.marginLeft).toBe("auto");
    expect(img.style.marginRight).toBe("0px");
    expect(imgWrapper.style.textAlign).toBe("right");
  });
});
