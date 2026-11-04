"use client";

import { useEffect, useState } from "react";
import { getPrivacyConfiguration } from "@/lib/api-platform";
import type { PrivacyConfiguration } from "@/lib/types-platform";

type State = { status: "loading" } | { status: "unreachable" } | { status: "ready"; config: PrivacyConfiguration };

function usePrivacyConfiguration(): State {
  const [state, setState] = useState<State>({ status: "loading" });
  useEffect(() => {
    let active = true;
    getPrivacyConfiguration()
      .then(config => { if (active) setState({ status: "ready", config }); })
      .catch(() => { if (active) setState({ status: "unreachable" }); });
    return () => { active = false; };
  }, []);
  return state;
}

/**
 * Who answers for this installation. Each install is run by someone different,
 * so this comes from the running service. An unset contact looks unset: a blank
 * here must not read as though a contact were given.
 */
export function GrievanceOfficer() {
  const state = usePrivacyConfiguration();
  if (state.status === "loading") return <p className="doc-muted" role="status">Checking this installation&hellip;</p>;
  if (state.status === "unreachable") {
    return (
      <div className="notice-unset" role="status">
        <strong>This page cannot reach an installation right now.</strong>
        <p>The contact is set by whoever runs the installation you use. Open this page from that installation, or ask its administrator.</p>
      </div>
    );
  }
  const { grievance, data_fiduciary: fiduciary } = state.config;
  return (
    <>
      <dl className="doc-facts">
        <div><dt>Who runs this installation</dt><dd>{fiduciary ?? <em className="unset-value">Not named by the operator</em>}</dd></div>
      </dl>
      {grievance.configured ? (
        <dl className="doc-facts">
          <div><dt>Grievance officer</dt><dd>{grievance.name}</dd></div>
          {grievance.email && <div><dt>Email</dt><dd><a href={`mailto:${grievance.email}`}>{grievance.email}</a></dd></div>}
          {grievance.phone && <div><dt>Phone</dt><dd><a href={`tel:${grievance.phone}`}>{grievance.phone}</a></dd></div>}
          {grievance.address && <div><dt>Address</dt><dd>{grievance.address}</dd></div>}
        </dl>
      ) : (
        <div className="notice-unset" role="status">
          <strong>No grievance officer has been named for this installation.</strong>
          <p>
            The operator has not set this yet, so there is no contact to give you here. If you run this installation,
            set <code>GRIEVANCE_OFFICER_NAME</code> and <code>GRIEVANCE_OFFICER_EMAIL</code> in its environment. If you
            use it, ask whoever gave you access.
          </p>
        </div>
      )}
    </>
  );
}

export function RetentionStatement() {
  const state = usePrivacyConfiguration();
  if (state.status !== "ready") {
    return <p>Conversations are kept until you delete them, unless the operator of your installation has set a retention period.</p>;
  }
  const { chat_retention_days: days, chats_kept_until_deleted: keep } = state.config.retention;
  return keep
    ? <p>On this installation, conversations are kept until you delete them or erase your account. The operator has not set an automatic retention period.</p>
    : <p>On this installation, a conversation with no activity for <strong>{days} days</strong> is erased automatically, along with the background records it left behind.</p>;
}
