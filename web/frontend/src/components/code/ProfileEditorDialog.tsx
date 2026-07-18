/**
 * ProfileEditorDialog — встроенный редактор xray-профиля панели.
 *
 * Полноэкранная модалка в стиле панели: CodeMirror со схемой xray,
 * секции-навигация, валидация, история версий (наша БД), diff перед
 * сохранением, инфо о нодах на профиле. Сохранение — PATCH в панель
 * через наш бэкенд (аудит + снапшот версии на бэке).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { EditorView } from '@codemirror/view'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { resourcesApi, ConfigProfile, ConfigVersion } from '@/api/resources'
import client from '@/api/client'
import { CodeEditor } from './CodeEditor'
import { CodeDiff } from './CodeDiff'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Server, History, AlertTriangle, Check, RotateCcw } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

interface Props {
  profile: ConfigProfile | null
  onClose: () => void
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 16).replace('T', ' ')
}

export function ProfileEditorDialog({ profile, onClose }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [text, setText] = useState('')
  const [original, setOriginal] = useState('')
  const [diffOpen, setDiffOpen] = useState(false)
  const [errorCount, setErrorCount] = useState(0)

  // конфиг профиля из панели
  const { data: profileData, isLoading } = useQuery({
    queryKey: ['config-profile', profile?.uuid],
    queryFn: () => resourcesApi.getConfigProfile(profile!.uuid),
    enabled: !!profile,
    staleTime: 0,
  })

  // ноды, сидящие на профиле (интеграция с ремнёй)
  const { data: nodes } = useQuery({
    queryKey: ['nodes-brief-profiles'],
    queryFn: async () => {
      const { data } = await client.get('/nodes', { params: { per_page: 500 } })
      return (data.items || data) as Record<string, any>[]
    },
    enabled: !!profile,
    staleTime: 60_000,
  })
  const profileNodes = useMemo(() => {
    if (!profile || !nodes) return []
    return nodes.filter((n) => {
      const uuid = n.configProfile?.activeConfigProfileUuid || n.activeConfigProfileUuid
      return uuid === profile.uuid
    }).map((n) => String(n.name || n.uuid))
  }, [nodes, profile])

  // история версий (наша БД)
  const { data: versions, refetch: refetchVersions } = useQuery({
    queryKey: ['config-profile-versions', profile?.uuid],
    queryFn: () => resourcesApi.getProfileVersions(profile!.uuid),
    enabled: !!profile,
    staleTime: 30_000,
  })

  // загрузка конфига в редактор
  useEffect(() => {
    if (!profileData) return
    const cfg = profileData.config
      ?? profileData.configProfile?.config
      ?? profileData.response?.config
    const pretty = cfg ? JSON.stringify(cfg, null, 2) : ''
    setText(pretty)
    setOriginal(pretty)
  }, [profileData])

  // секции конфига для навигации
  const sections = useMemo(() => {
    try {
      const parsed = JSON.parse(text)
      return Object.keys(parsed).map((k) => ({
        key: k,
        count: Array.isArray(parsed[k]) ? parsed[k].length : null,
      }))
    } catch {
      return []
    }
  }, [text])

  const cmRef = useRef<EditorView | null>(null)
  const jumpTo = (key: string) => {
    const view = cmRef.current
    const idx = text.indexOf(`"${key}"`)
    if (!view || idx < 0) return
    view.dispatch({
      selection: { anchor: idx },
      effects: EditorView.scrollIntoView(idx, { y: 'start', yMargin: 8 }),
    })
    view.focus()
  }

  const formatJson = () => {
    try {
      setText(JSON.stringify(JSON.parse(text), null, 2))
    } catch {
      toast.error(t('resources.editor.invalidJson'))
    }
  }

  const loadVersion = async (v: ConfigVersion) => {
    try {
      const full = await resourcesApi.getProfileVersion(v.id)
      setText(full.content)
      toast.info(t('resources.editor.versionLoaded', { date: fmtDate(v.created_at) }))
    } catch {
      toast.error(t('common.error'))
    }
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(text) // проверено до открытия диффа
      await resourcesApi.updateConfigProfile(profile!.uuid, parsed)
    },
    onSuccess: () => {
      toast.success(t('resources.editor.saved'))
      setDiffOpen(false)
      setOriginal(text)
      qc.invalidateQueries({ queryKey: ['config-profiles'] })
      qc.invalidateQueries({ queryKey: ['config-profile', profile?.uuid] })
      refetchVersions()
    },
    onError: () => toast.error(t('resources.editor.saveError')),
  })

  const dirty = text !== original
  const canSave = dirty && errorCount === 0 && !!text.trim()

  const openDiff = () => {
    try {
      JSON.parse(text)
    } catch {
      toast.error(t('resources.editor.invalidJson'))
      return
    }
    setDiffOpen(true)
  }

  return (
    <>
      <Dialog open={profile !== null} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="w-[97vw] max-w-[1400px] h-[92vh] flex flex-col gap-3 p-4 sm:p-5">
          <DialogHeader className="shrink-0">
            <div className="flex items-center gap-2 flex-wrap pr-8">
              <DialogTitle className="text-base">{profile?.name}</DialogTitle>
              {profileNodes.length > 0 && (
                <Badge variant="outline" className="text-[10px] text-primary-300 gap-1">
                  <Server className="w-3 h-3" />
                  {t('resources.editor.usedByNodes', { count: profileNodes.length })}
                </Badge>
              )}
              {errorCount > 0 ? (
                <Badge className="bg-red-500/20 text-red-300 text-[10px] gap-1">
                  <AlertTriangle className="w-3 h-3" /> {t('resources.editor.errors', { count: errorCount })}
                </Badge>
              ) : text.trim() ? (
                <Badge className="bg-green-500/20 text-green-300 text-[10px] gap-1">
                  <Check className="w-3 h-3" /> {t('resources.editor.valid')}
                </Badge>
              ) : null}
            </div>
            {profileNodes.length > 0 && (
              <p className="text-[11px] text-muted-foreground">
                {t('resources.editor.nodesHint', { nodes: profileNodes.join(', ') })}
              </p>
            )}
          </DialogHeader>

          <div className="flex-1 min-h-0 flex gap-3">
            {/* секции-навигация */}
            {sections.length > 0 && (
              <div className="hidden md:flex flex-col gap-0.5 w-44 shrink-0 overflow-y-auto">
                {sections.map((s) => (
                  <button key={s.key} type="button" onClick={() => jumpTo(s.key)}
                    className="text-left px-2.5 py-1.5 rounded-md text-xs text-muted-foreground hover:text-white hover:bg-white/5 transition-colors font-mono">
                    {s.key}
                    {s.count != null && <span className="text-primary-400 ml-1">[{s.count}]</span>}
                  </button>
                ))}
              </div>
            )}
            {/* редактор */}
            <div className="flex-1 min-h-0">
              {isLoading ? (
                <Skeleton className="h-full w-full" />
              ) : (
                <CodeEditor value={text} onChange={setText} schema="xray" onDiagnostics={setErrorCount} viewRef={cmRef} />
              )}
            </div>
          </div>

          <DialogFooter className="shrink-0 flex-wrap gap-2 sm:justify-between">
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={formatJson}>
                {t('resources.editor.format')}
              </Button>
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
                    <DropdownMenuItem key={v.id} onClick={() => loadVersion(v)} className="gap-2">
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
              <Button disabled={!canSave} onClick={openDiff}>
                {t('resources.editor.reviewAndSave')}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* diff перед сохранением */}
      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent className="w-[97vw] max-w-[1400px] h-[88vh] flex flex-col gap-3 p-4 sm:p-5">
          <DialogHeader className="shrink-0">
            <DialogTitle className="text-base">{t('resources.editor.diffTitle')}</DialogTitle>
            <p className={cn('text-[11px]', profileNodes.length ? 'text-amber-300' : 'text-muted-foreground')}>
              {profileNodes.length > 0
                ? t('resources.editor.diffWarnNodes', { count: profileNodes.length })
                : t('resources.editor.diffHint')}
            </p>
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
    </>
  )
}
