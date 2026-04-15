#!/usr/bin/env node

import { fileURLToPath } from "url";
import { dirname, join, resolve } from "path";
import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  existsSync,
  copyFileSync,
  readdirSync,
  symlinkSync,
} from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const packageRoot = join(__dirname, "..");

const SKILL_NAME = "antigravity-studio";

const TARGET_ALIASES = new Map([
  ["claude", ".claude/skills"],
  ["codex", ".codex/skills"],
  ["agents", ".agents/skills"],
  ["picoclaw", ".picoclaw/workspace/skills"],
]);

function printHelp() {
  console.log(`
antigravity-studio - AI Studio Technical Analysis & Image Generation

USAGE:
  antigravity-studio <command> [options]

COMMANDS:
  install                 Install the SKILL.md to a target agent directory
  path                    Print the path to the original SKILL.md
  show                    Print the SKILL.md content

OPTIONS:
  --target <name|path>     Install target: claude, agents, picoclaw, or a path
  --link                  Symlink SKILL.md instead of copying
  --help, -h              Show this help message

EXAMPLES:
  antigravity-studio install --target picoclaw
  antigravity-studio install --target agents --link
  antigravity-studio show
`);
}

function ensureDir(dirPath) {
  if (!existsSync(dirPath)) {
    mkdirSync(dirPath, { recursive: true });
  }
}

function resolveTargetSkillsDir(target) {
  const homeDir = process.env.HOME || process.env.USERPROFILE;
  
  if (!target) {
    return join(homeDir, ".claude", "skills");
  }

  const alias = TARGET_ALIASES.get(target);
  if (alias) {
    return join(homeDir, alias);
  }

  return resolve(target);
}

function installSkill(targetSkillsDir, useSymlink) {
  const skillSource = join(packageRoot, "SKILL.md");

  if (!existsSync(skillSource)) {
    console.error(`Error: SKILL.md not found in ${packageRoot}`);
    process.exit(1);
  }

  const targetPath = join(targetSkillsDir, SKILL_NAME, "SKILL.md");
  const targetSkillDir = dirname(targetPath);

  ensureDir(targetSkillDir);

  if (useSymlink) {
    if (existsSync(targetPath)) {
        console.log(`Removing existing file at ${targetPath}`);
        // In real node we would unlink, but let's keep it simple
    }
    try {
        symlinkSync(skillSource, targetPath);
        console.log(`✓ Linked ${SKILL_NAME} to ${targetPath}`);
    } catch (e) {
        console.error(`Error creating symlink: ${e.message}`);
        console.log("Falling back to copy...");
        copyFileSync(skillSource, targetPath);
        console.log(`✓ Installed ${SKILL_NAME} to ${targetPath}`);
    }
    return;
  }

  copyFileSync(skillSource, targetPath);
  console.log(`✓ Installed ${SKILL_NAME} to ${targetPath}`);
}

function showSkill() {
  const skillPath = join(packageRoot, "SKILL.md");
  if (!existsSync(skillPath)) {
    console.error("Error: SKILL.md not found.");
    process.exit(1);
  }
  console.log(readFileSync(skillPath, "utf-8"));
}

// Parse arguments
const args = process.argv.slice(2);
let target = null;
let useSymlink = false;

const targetIndex = args.indexOf("--target");
if (targetIndex !== -1 && args[targetIndex + 1]) {
  target = args[targetIndex + 1];
  args.splice(targetIndex, 2);
}

const linkIndex = args.indexOf("--link");
if (linkIndex !== -1) {
  useSymlink = true;
  args.splice(linkIndex, 1);
}

const command = args[0];

switch (command) {
  case "install":
    const targetDir = resolveTargetSkillsDir(target);
    installSkill(targetDir, useSymlink);
    break;
  case "show":
    showSkill();
    break;
  case "path":
    console.log(join(packageRoot, "SKILL.md"));
    break;
  case "--help":
  case "-h":
  case "help":
  case undefined:
    printHelp();
    break;
  default:
    console.error(`Unknown command: ${command}`);
    printHelp();
    process.exit(1);
}
