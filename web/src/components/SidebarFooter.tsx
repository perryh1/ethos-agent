import { Typography } from "@nous-research/ui/ui/components/typography/index";
import type { StatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n";

// Ethos is its own distribution, so the label says Ethos and the link has to go
// to Ethos. Upstream is credited in NOTICE, ETHOS.md and the installer banner
// rather than by pointing a link labelled "Ethos" at someone else's site.
const PROJECT_URL = "https://github.com/perryh1/ethos-agent";

/** What the footer shows, and what it reveals on hover.
 *
 * The Ethos version leads because this is an Ethos install. The Hermes core
 * version it is built on stays one hover away rather than being dropped, so
 * provenance is never hidden. An older gateway sends no `ethos_version`, in
 * which case the core version is shown alone exactly as before.
 */
function versionLabel(status: StatusResponse | null): {
  text: string;
  title?: string;
} {
  if (status?.ethos_version != null) {
    return {
      text: `v${status.ethos_version}`,
      title:
        status.version != null
          ? `Ethos ${status.ethos_version} · Hermes Agent core ${status.version}`
          : undefined,
    };
  }
  if (status?.version != null) return { text: `v${status.version}` };
  return { text: "—" };
}

export function SidebarFooter({ status }: SidebarFooterProps) {
  const { t } = useI18n();
  const version = versionLabel(status);

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-between gap-2",
        "px-5 py-2.5",
        "border-t border-current/10",
      )}
    >
      <Typography
        className="font-mono-ui text-xs tabular-nums tracking-[0.08em] text-text-tertiary lowercase"
        title={version.title}
      >
        {version.text}
      </Typography>

      <a
        href={PROJECT_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "font-sans text-display text-xs tracking-[0.12em] text-midground",
          "transition-opacity hover:opacity-90",
          "focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-midground/40",
        )}
      >
        {t.app.footer.org}
      </a>
    </div>
  );
}

interface SidebarFooterProps {
  status: StatusResponse | null;
}
