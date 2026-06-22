import React, { useEffect, useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { useShipIdRulesStore } from '../store/shipIdRulesStore';
import { PatternTable } from './PatternTable';
import { BlacklistSection } from './BlacklistSection';
import { ConvertMapTable } from './ConvertMapTable';
import { Button } from '../../../components/Button/Button';

type CardKey = 'patterns' | 'blacklist' | 'convert';

export const RecognitionConfigSection: React.FC = () => {
  const { patterns, fetchAll, isLoading, forceReload } = useShipIdRulesStore();
  const [expanded, setExpanded] = useState<Record<CardKey, boolean>>({
    patterns: true,
    blacklist: false,
    convert: false,
  });
  const [reloading, setReloading] = useState(false);
  const [reloadMsg, setReloadMsg] = useState<string | null>(null);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const toggle = (key: CardKey) => setExpanded((s) => ({ ...s, [key]: !s[key] }));

  const handleReload = async () => {
    setReloading(true);
    setReloadMsg(null);
    try {
      const reloaded = await forceReload();
      setReloadMsg(reloaded ? 'Pipeline đã reload rules mới.' : 'Rules chưa thay đổi, không cần reload.');
    } catch {
      setReloadMsg('Reload thất bại.');
    } finally {
      setReloading(false);
      setTimeout(() => setReloadMsg(null), 4000);
    }
  };

  const activePatterns = patterns.filter((p) => p.is_active).length;

  const Card: React.FC<{
    id: CardKey;
    title: string;
    badge?: string;
    children: React.ReactNode;
  }> = ({ id, title, badge, children }) => (
    <div className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden">
      <button
        type="button"
        onClick={() => toggle(id)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-white/5 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
      >
        <span className="text-sm font-semibold flex items-center gap-2">
          {title}
          {badge ? (
            <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 text-[10px] font-bold">
              {badge}
            </span>
          ) : null}
        </span>
        {expanded[id] ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>
      {expanded[id] ? <div className="p-4">{children}</div> : null}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Cấu hình nhận diện mã tàu từ OCR — thay đổi có hiệu lực trong tối đa 30 giây hoặc sau khi nhấn Reload.
        </p>
        <div className="flex items-center gap-3">
          {reloadMsg ? (
            <span className="text-xs text-emerald-600 dark:text-emerald-400">{reloadMsg}</span>
          ) : null}
          <Button
            type="button"
            variant="outline"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5"
            disabled={reloading || isLoading}
            onClick={() => void handleReload()}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${reloading ? 'animate-spin' : ''}`} />
            Reload ngay
          </Button>
        </div>
      </div>

      <Card id="patterns" title="Regex Patterns" badge={`${activePatterns} active`}>
        <PatternTable />
      </Card>

      <Card id="blacklist" title="Blacklist">
        <BlacklistSection />
      </Card>

      <Card id="convert" title="Convert Map">
        <ConvertMapTable />
      </Card>
    </div>
  );
};
