"use client";
import { useCitizenLang } from "./citizen/useCitizenLang";

export default function UploadPrivacy({ citizen = false }: { citizen?: boolean }) {
  const { t } = useCitizenLang(citizen);
  return <div className="privacy-copy"><p>{t("privacyProcessing")}</p><p>{t("privacyMemory")}</p><p>{t("privacyRecords")}</p><p>{t("privacyListen")}</p></div>;
}
