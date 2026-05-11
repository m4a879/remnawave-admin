// @ts-nocheck
import React from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button as ShadButton } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Button } from './Button';
import { Icon } from './Icon';

/**
 * Compatibility wrapper that preserves the upstream xray-editor's Modal API
 * but renders through the admin panel's shadcn/Radix Dialog underneath.
 *
 * We override Dialog's default `max-w-lg` so the xray editor's wide content
 * (config dashboards, JSON editors, dual-pane forms) still fits. A local
 * fullscreen toggle stays on the title bar — Radix doesn't ship one out of
 * the box and the editor relies on going full-window for the JSON view.
 */
export const Modal = ({
    title,
    onClose,
    onSave,
    children,
    extraButtons = null,
    className = '',
    isSecondary = false,
}) => {
    const [isFullScreen, setIsFullScreen] = React.useState(false);

    return (
        <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
            <DialogContent
                onEscapeKeyDown={(e) => { e.preventDefault(); onClose(); }}
                onInteractOutside={(e) => {
                    // Don't auto-close when the inner content is being interacted with
                    // (toast portals, dnd drag layers, etc).
                    if ((e.target as HTMLElement)?.closest?.('[data-radix-portal]')) {
                        e.preventDefault();
                    }
                }}
                className={cn(
                    // Cancel shadcn defaults: no narrow max-w, no auto bottom-sheet on mobile
                    'p-0 bg-slate-900 border border-slate-700 shadow-2xl flex flex-col gap-0',
                    'max-w-[95vw] xl:max-w-[75vw] 2xl:max-w-[1400px]',
                    'h-full md:h-auto md:max-h-[90vh] md:rounded-2xl',
                    'sm:bottom-auto sm:left-[50%] sm:right-auto sm:top-[50%] sm:translate-x-[-50%] sm:translate-y-[-50%]',
                    isSecondary && 'bg-slate-900/95',
                    isFullScreen && 'h-full md:h-screen md:max-h-screen md:max-w-full md:w-full md:rounded-none is-modal-fullscreen',
                    className,
                )}
            >
                <DialogHeader className="flex-row justify-between items-center p-4 md:p-5 border-b border-slate-800 shrink-0 text-left space-y-0">
                    <div className="flex items-center gap-3 min-w-0 relative z-10">
                        <DialogTitle className="text-lg md:text-xl font-bold text-white flex items-center gap-2 truncate">
                            <Icon name="PencilSimple" className="text-indigo-400 shrink-0" /> {title}
                        </DialogTitle>
                        <button
                            type="button"
                            onClick={() => setIsFullScreen(!isFullScreen)}
                            title={isFullScreen ? 'Выйти из полноэкранного режима' : 'На весь экран'}
                            className="text-slate-500 hover:text-indigo-400 p-1.5 hover:bg-slate-800 rounded-lg transition-all hidden md:block"
                        >
                            <Icon name={isFullScreen ? 'CornersIn' : 'CornersOut'} className="text-base" />
                        </button>
                    </div>
                </DialogHeader>

                <div
                    className={cn(
                        'flex-1 relative flex flex-col min-h-0 custom-scroll',
                        isFullScreen ? 'p-1' : 'p-4 md:p-6',
                        className?.includes?.('overflow-hidden') ? 'overflow-hidden' : 'overflow-y-auto',
                    )}
                >
                    {children}
                </div>

                <DialogFooter className="p-4 md:p-5 border-t border-slate-800 flex-col-reverse md:flex-row md:justify-between items-center bg-slate-900 md:rounded-b-2xl shrink-0 gap-3 md:gap-0 z-20 sm:space-x-0">
                    <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0 hide-scrollbar relative z-10">
                        {extraButtons}
                    </div>
                    <div className="flex gap-3 w-full md:w-auto relative z-10">
                        <ShadButton variant="secondary" onClick={onClose} className="flex-1 md:flex-none">
                            Закрыть
                        </ShadButton>
                        {onSave && onSave !== onClose && (
                            <Button variant="success" onClick={onSave} icon="FloppyDisk" className="flex-1 md:flex-none">
                                Сохранить
                            </Button>
                        )}
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
