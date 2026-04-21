import { describe, expect, it, vi } from 'vitest';

import { copyProcessTemplatePrompt } from './ProcessTemplatesPage';

describe('ProcessTemplatesPage prompt copy', () => {
  it('copies the current generated prompt', async () => {
    const clipboard = { writeText: vi.fn(async () => {}) };

    await expect(copyProcessTemplatePrompt('edited prompt body', clipboard as never)).resolves.toBeUndefined();

    expect(clipboard.writeText).toHaveBeenCalledWith('edited prompt body');
  });

  it('rejects empty prompt content before touching the clipboard', async () => {
    const clipboard = { writeText: vi.fn(async () => {}) };

    await expect(copyProcessTemplatePrompt('  ', clipboard as never)).rejects.toThrow('请先生成 Prompt。');

    expect(clipboard.writeText).not.toHaveBeenCalled();
  });

  it('surfaces a copy failure when clipboard and fallback copy both fail', async () => {
    const originalDocument = globalThis.document;
    const execCommand = vi.fn(() => false);
    const appendChild = vi.fn();
    const removeChild = vi.fn();
    const textArea = {
      value: '',
      setAttribute: vi.fn(),
      style: {},
      focus: vi.fn(),
      select: vi.fn(),
    };
    const clipboard = { writeText: vi.fn(async () => { throw new Error('denied'); }) };
    (globalThis as any).document = {
      createElement: vi.fn(() => textArea),
      body: { appendChild, removeChild },
      execCommand,
    };

    try {
      await expect(copyProcessTemplatePrompt('prompt body', clipboard as never))
        .rejects.toThrow('浏览器未能自动复制，请检查页面权限。');

      expect(clipboard.writeText).toHaveBeenCalledWith('prompt body');
      expect(execCommand).toHaveBeenCalledWith('copy');
    } finally {
      (globalThis as any).document = originalDocument;
    }
  });
});
