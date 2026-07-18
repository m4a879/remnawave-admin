/**
 * TemplateEditorDialog — встроенный редактор шаблона подписки.
 *
 * Те же плюшки, что у редактора профилей: секции-навигация (для JSON),
 * валидация, история версий (наша БД) с диффом/откатом, diff перед
 * сохранением, Ctrl+S. YAML-типы (MIHOMO/CLASH/STASH) редактируются как
 * YAML (encodedTemplateYaml, base64).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { EditorView } from '@codemirror/view'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { resourcesApi, Template, ConfigVersion } from '@/api/resources'
import { b64DecodeUtf8, b64EncodeUtf8 } from '@/lib/base64'
import { CodeEditor } from './CodeEditor'
import { CodeDiff } from './CodeDiff'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { History, AlertTriangle, Check, RotateCcw } from '@/components/brand/icons'

const YAML_TYPES = ['MIHOMO', 'CLASH', 'STASH']

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 16).replace('T', ' ')
}

export function TemplateEditorDialog({ template, onClose }: { template: Template | null; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const isYaml = !!template && YAML_TYPES.includes(template.templateType)
  const [text, setText] = useState('')
  const [original, setOriginal] = useState('')
  const [name, setName] = useState('')
  const [errorCount, setErrorCount] = useState(0)
  const [diffOpen, setDiffOpen] = useState(false)
  const [versionPreview, setVersionPreview] = useState<{ meta: ConfigVersion; content: string } | null>(null)
  const cmRef = useRef<EditorView | null>(null)

  const { data: full, isLoading } = useQuery({
    queryKey: ['template-full', template?.uuid],
    queryFn: () => resourcesApi.getTemplate(template!.uuid),
    enabled: !!template,
    staleTime: 0,
  })
  const { data: versions, refetch: refetchVersions } = useQuery({
    queryKey: ['template-versions', template?.uuid],
    queryFn: () => resourcesApi.getTemplateVersions(template!.uuid),
    enabled: !!template,
    staleTime: 30_000,
  })

  useEffect(() => {
    if (!full) return
    const content = full.encodedTemplateYaml
      ? b64DecodeUtf8(full.encodedTemplateYaml)
      : JSON.stringify(full.templateJson ?? {}, null, 2)
    setText(content)
    setOriginal(content)
    setName(full.name)
  }, [full])

  // секции-навигация (только для валидного JSON)
  const sections = useMemo(() => {
    if (isYaml) return []
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed !== 'object' || Array.isArray(parsed) || !parsed) return []
      return Object.keys(parsed).map((k) => ({
        key: k, count: Array.isArray(parsed[k]) ? parsed[k].length : null,
      }))
    } catch {
      return []
    }
  }, [text, isYaml])

  const jumpTo = (key: string) => {
    const cm = cmRef.current
    const idx = text.indexOf(`"${key}"`)
    if (!cm || idx < 0) return
    cm.dispatch({ selection: { anchor: idx }, effects: EditorView.scrollIntoView(idx, { y: 'start', yMargin: 8 }) })
    cm.focus()
  }

  const formatJson = () => {
    if (isYaml) return
    try {
      setText(JSON.stringify(JSON.parse(text), null, 2))
    } catch {
      toast.error(t('resources.editor.invalidJson'))
    }
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      if (isYaml) {
        await resourcesApi.updateTemplate(template!.uuid, { name, encodedTemplateYaml: b64EncodeUtf8(text) })
      } else {
        await resourcesApi.updateTemplate(template!.uuid, { name, templateJson: JSON.parse(text) })
      }
    },
    onSuccess: () => {
      toast.success(t('resources.editor.saved'))
      setDiffOpen(false)
      setOriginal(text)
      qc.invalidateQueries({ queryKey: ['templates'] })
      qc.invalidateQueries({ queryKey: ['template-full', template?.uuid] })
      refetchVersions()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('resources.editor.saveError')),
  })

  const dirty = text !== original || name !== (full?.name ?? '')
  const canSave = dirty && (isYaml || errorCount === 0) && !!text.trim() && !!name.trim()

  const openDiff = () => {
    if (!isYaml) {
      try { JSON.parse(text) } catch { toast.error(t('resources.editor.invalidJson')); return }
    }
    setDiffOpen(true)
  }

  useEffect(() => {
    if (!template) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (canSave) openDiff()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template, canSave, text, isYaml])

  const openVersionPreview = async (v: ConfigVersion) => {
    try {
      const fullV = await resourcesApi.getTemplateVersion(v.id)
      setVersionPreview({ meta: v, content: fullV.content })
    } catch {
      toast.error(t('common.error'))
    }
  }
  const loadPreviewedVersion = () => {
    if (!versionPreview) return
    setText(versionPreview.content)
    setVersionPreview(null)
    toast.info(t('resources.editor.versionLoaded', { date: fmtDate(versionPreview.meta.created_at) }))
  }

  return (
    <>
      <Dialog open={template !== null} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="w-[97vw] max-w-[1300px] h-[92vh] flex flex-col gap-3 p-4 sm:p-5">
          <DialogHeader className="shrink-0">
            <div className="flex items-center gap-2 flex-wrap pr-8">
              <DialogTitle className="text-base">{t('resources.templates.editTitle')}</DialogTitle>
              <Badge variant="outline" className="text-[10px]">
                {template?.templateType}{isYaml ? ' · YAML' : ' · JSON'}
              </Badge>
              {!isYaml && !isLoading && (errorCount > 0 ? (
                <Badge className="bg-red-500/20 text-red-300 text-[10px] gap-1">
                  <AlertTriangle className="w-3 h-3" /> {t('resources.editor.errors', { count: errorCount })}
                </Badge>
              ) : text.trim() ? (
                <Badge className="bg-green-500/20 text-green-300 text-[10px] gap-1">
                  <Check className="w-3 h-3" /> {t('resources.editor.valid')}
                </Badge>
              ) : null)}
            </div>
          </DialogHeader>

          <div className="shrink-0">
            <Label htmlFor="tplName">{t('resources.templates.nameLabel')}</Label>
            <Input id="tplName" value={name} className="mt-1" onChange={(e) => setName(e.target.value)} />
          </div>

          <div className="flex-1 min-h-0 flex gap-3">
            {sections.length > 0 && (
              <div className="hidden md:flex flex-col gap-0.5 w-44 shrink-0 overflow-y-auto">
                {sections.map((s) => (
                  <button key={s.key} type="button" onClick={() => jumpTo(s.key)}
                    className="text-left px-2.5 py-1.5 rounded-md text-xs text-muted-foreground hover:text-white hover:bg-white/5 transition-colors font-mono">
                    {s.key}{s.count != null && <span className="text-primary-400 ml-1">[{s.count}]</span>}
                  </button>
                ))}
              </div>
            )}
            <div className="flex-1 min-h-0">
              {isLoading ? (
                <Skeleton className="h-full w-full" />
              ) : (
                <CodeEditor
                  key={`${template?.uuid}-${isYaml ? 'yaml' : 'json'}`}
                  value={text} onChange={setText}
                  schema={isYaml ? 'yaml' : 'json'}
                  onDiagnostics={setErrorCount} viewRef={cmRef}
                />
              )}
            </div>
          </div>

          <DialogFooter className="shrink-0 flex-wrap gap-2 sm:justify-between">
            <div className="flex items-center gap-2">
              {!isYaml && (
                <Button variant="outline" size="sm" onClick={formatJson}>{t('resources.editor.format')}</Button>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <History className="w-4 h-4" />
                    {t('resources.editor.history')}
                    {(versions?.items.length ?? 0) > 0 && (
                      <span className="text-muted-foreground">({versions!.items.length})</span>
                    )}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
                  {!versions?.items.length ? (
                    <div className="px-3 py-2 text-xs text-muted-foreground">{t('resources.editor.noVersions')}</div>
                  ) : versions.items.map((v) => (
                    <DropdownMenuItem key={v.id} onClick={() => openVersionPreview(v)} className="gap-2">
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span className="font-mono text-xs">{fmtDate(v.created_at)}</span>
                      <span className="text-xs text-muted-foreground">{v.created_by || '—'}</span>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
              <Button disabled={!canSave} onClick={openDiff} title="Ctrl+S">
                {t('resources.editor.reviewAndSave')}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* diff перед сохранением */}
      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent className="w-[97vw] max-w-[1300px] h-[88vh] flex flex-col gap-3 p-4 sm:p-5">
          <DialogHeader className="shrink-0">
            <DialogTitle className="text-base">{t('resources.editor.diffTitle')}</DialogTitle>
            <p className="text-[11px] text-muted-foreground">{t('resources.editor.diffHint')}</p>
          </DialogHeader>
          <div className="flex-1 min-h-0">
            <CodeDiff original={original} modified={text} />
          </div>
          <DialogFooter className="shrink-0">
            <Button variant="outline" onClick={() => setDiffOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
              {saveMut.isPending ? t('common.saving') : t('resources.editor.confirmSave')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* предпросмотр версии из истории */}
      <Dialog open={versionPreview !== null} onOpenChange={(o) => !o && setVersionPreview(null)}>
        <DialogContent className="w-[97vw] max-w-[1300px] h-[88vh] flex flex-col gap-3 p-4 sm:p-5">
          <DialogHeader className="shrink-0">
            <DialogTitle className="text-base">
              {t('resources.editor.versionDiffTitle', {
                date: fmtDate(versionPreview?.meta.created_at ?? null),
                author: versionPreview?.meta.created_by || '—',
              })}
            </DialogTitle>
            <p className="text-[11px] text-muted-foreground">{t('resources.editor.versionDiffHint')}</p>
          </DialogHeader>
          <div className="flex-1 min-h-0">
            {versionPreview && <CodeDiff original={text} modified={versionPreview.content} />}
          </div>
          <DialogFooter className="shrink-0">
            <Button variant="outline" onClick={() => setVersionPreview(null)}>{t('common.cancel')}</Button>
            <Button onClick={loadPreviewedVersion}>
              <RotateCcw className="w-4 h-4 mr-1.5" /> {t('resources.editor.loadVersion')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
