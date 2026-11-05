"use client";

import { PageHead, usePro } from "./context";
import type { ChatView } from "./ProApp";

/** The law, and nothing else. A chat that may read a case's files lives inside that case. */
export default function ResearchScreen({ chatView }: { chatView: ChatView }) {
  const { noun } = usePro();
  return (
    <div className="pro-page is-chat">
      <PageHead
        title="Research"
        lead={<>Reads the law only, and no {noun} files. To ask about your own files, open the {noun} and use Ask.</>}
        eyebrow="Law only"
      />
      {chatView({ caseId: null })}
    </div>
  );
}

