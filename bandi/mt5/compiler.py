"""
MQL5 Compiler Automation for BANDI.
Discovers local MetaTrader 5 installations, copies Bandi.mq5 into the Experts folder,
invokes MetaEditor64.exe with standard include paths to compile into Bandi.ex5,
and verifies log diagnostics.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from bandi.config import settings

logger = logging.getLogger("bandi.compiler")


class MQL5Compiler:
    def __init__(self):
        self.metaeditor_path = Path(settings.MT5_METAEDITOR_PATH)
        self.source_mq5 = settings.BASE_DIR / "bandi" / "mql5" / "Experts" / "Bandi.mq5"
        self.appdata = Path(os.environ.get("APPDATA", ""))
        self.terminal_base = self.appdata / "MetaQuotes" / "Terminal"

    def find_terminal_expert_dirs(self) -> List[Path]:
        """Discover all MQL5/Experts directories in user's MetaTrader 5 profiles."""
        found: List[Path] = []
        if not self.terminal_base.exists():
            return found

        for entry in self.terminal_base.iterdir():
            if entry.is_dir() and entry.name not in ("Common", "Community"):
                experts_dir = entry / "MQL5" / "Experts"
                if experts_dir.exists():
                    found.append(experts_dir)
        return found

    def compile_ea(self) -> Dict[str, Any]:
        """
        Deploy and compile Bandi.mq5 across detected MetaTrader 5 installations.
        """
        if not self.source_mq5.exists():
            return {"ok": False, "error": f"Source file not found at {self.source_mq5}"}

        if not self.metaeditor_path.exists():
            return {"ok": False, "error": f"MetaEditor not found at {self.metaeditor_path}"}

        expert_dirs = self.find_terminal_expert_dirs()
        if not expert_dirs:
            return {"ok": False, "error": f"No MT5 MQL5/Experts folders found in {self.terminal_base}"}

        results = []
        overall_ok = True

        for target_dir in expert_dirs:
            target_mq5 = target_dir / "Bandi.mq5"
            target_ex5 = target_dir / "Bandi.ex5"
            target_log = target_dir / "Bandi_compile.log"
            mql5_root = target_dir.parent  # ...\MQL5

            # Copy source file to terminal directory
            try:
                shutil.copy2(str(self.source_mq5), str(target_mq5))
            except Exception as e:
                logger.error("Failed to copy Bandi.mq5 to %s: %s", target_dir, e)
                continue

            # Execute MetaEditor compilation with include flag for this terminal
            cmd = f'"{self.metaeditor_path}" /compile:"{target_mq5}" /inc:"{mql5_root}" /log:"{target_log}"'
            logger.info("Executing MetaEditor compilation: %s", cmd)

            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    timeout=120.0
                )

                # Read log (MetaEditor produces UTF-16 log)
                log_content = ""
                if target_log.exists():
                    try:
                        with open(target_log, "rb") as f:
                            raw = f.read()
                            log_content = raw.decode("utf-16", errors="ignore").strip()
                    except Exception:
                        log_content = "Log created but failed to decode."

                compiled = target_ex5.exists() and "0 errors" in log_content

                res_item = {
                    "terminal_dir": str(target_dir),
                    "compiled": compiled,
                    "ex5_exists": target_ex5.exists(),
                    "log": log_content
                }
                results.append(res_item)

                if not compiled:
                    overall_ok = False

            except Exception as e:
                logger.error("Exception compiling in %s: %s", target_dir, e)
                results.append({"terminal_dir": str(target_dir), "compiled": False, "error": str(e)})
                overall_ok = False

        return {
            "ok": overall_ok,
            "terminals_processed": len(results),
            "details": results
        }


# Global compiler instance
mql5_compiler = MQL5Compiler()
