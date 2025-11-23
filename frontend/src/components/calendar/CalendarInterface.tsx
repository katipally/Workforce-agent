import { useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../../lib/api'

interface CalendarEventTime {
  dateTime?: string
  date?: string
}

interface CalendarEventAttendee {
  email?: string
  displayName?: string
  responseStatus?: string
}

interface CalendarEventOrganizer {
  email?: string
  displayName?: string
}

interface CalendarEvent {
  id: string
  status?: string
  htmlLink?: string
  summary?: string
  description?: string
  location?: string
  start?: CalendarEventTime
  end?: CalendarEventTime
  organizer?: CalendarEventOrganizer
  attendees?: CalendarEventAttendee[]
  hangoutLink?: string
  conferenceData?: any
}

type CalendarView = 'day' | 'week' | 'month'

function formatDateForApi(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function parseEventDate(time?: CalendarEventTime): Date | null {
  if (!time) return null
  if (time.dateTime) {
    const d = new Date(time.dateTime)
    return Number.isNaN(d.getTime()) ? null : d
  }
  if (time.date) {
    const d = new Date(time.date)
    return Number.isNaN(d.getTime()) ? null : d
  }
  return null
}

function formatEventTimeRange(ev: CalendarEvent): string {
  const start = parseEventDate(ev.start)
  const end = parseEventDate(ev.end)

  if (!start && !end) return ''

  const opts: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
  }

  if (start && end) {
    const sameDay =
      start.getFullYear() === end.getFullYear() &&
      start.getMonth() === end.getMonth() &&
      start.getDate() === end.getDate()

    if (sameDay) {
      return `${start.toLocaleTimeString(undefined, opts)} - ${end.toLocaleTimeString(undefined, opts)}`
    }
  }

  if (start && !end) {
    return start.toLocaleTimeString(undefined, opts)
  }

  if (!start && end) {
    return end.toLocaleTimeString(undefined, opts)
  }

  return ''
}

function formatEventDateLabel(ev: CalendarEvent): string {
  const start = parseEventDate(ev.start)
  if (!start) return ''
  return start.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

function getDayKey(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export default function CalendarInterface() {
  const [view, setView] = useState<CalendarView>('day')
  const [selectedDate, setSelectedDate] = useState<Date>(() => new Date())
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const todayKey = getDayKey(new Date())
  const selectedKey = getDayKey(selectedDate)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        setLoading(true)
        setError(null)

        const dateStr = formatDateForApi(selectedDate)
        const effectiveView = view === 'day' ? 'week' : view
        const params = new URLSearchParams({ view: effectiveView, date: dateStr })

        const res = await fetch(`${API_BASE_URL}/api/calendar/events?${params.toString()}`, {
          credentials: 'include',
        })

        if (!res.ok) {
          let detail: any = null
          try {
            detail = await res.json()
          } catch {
            // ignore
          }
          throw new Error(detail?.detail || 'Failed to load calendar events')
        }

        const json = (await res.json()) as { events?: CalendarEvent[] }
        if (!cancelled) {
          const list = json.events || []
          setEvents(list)
          if (selectedEvent) {
            const stillExists = list.find((e) => e.id === selectedEvent.id)
            if (!stillExists) setSelectedEvent(null)
          }
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message || 'Failed to load calendar events')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [view, selectedDate, selectedEvent])

  const groupedByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const ev of events) {
      const start = parseEventDate(ev.start)
      const key = start ? getDayKey(start) : 'unknown'
      const list = map.get(key) || []
      list.push(ev)
      map.set(key, list)
    }
    return map
  }, [events])

  const handlePrev = () => {
    const d = new Date(selectedDate)
    if (view === 'day') {
      d.setDate(d.getDate() - 1)
    } else if (view === 'week') {
      d.setDate(d.getDate() - 7)
    } else {
      d.setMonth(d.getMonth() - 1)
    }
    setSelectedDate(d)
  }

  const handleNext = () => {
    const d = new Date(selectedDate)
    if (view === 'day') {
      d.setDate(d.getDate() + 1)
    } else if (view === 'week') {
      d.setDate(d.getDate() + 7)
    } else {
      d.setMonth(d.getMonth() + 1)
    }
    setSelectedDate(d)
  }

  const handleToday = () => {
    setSelectedDate(new Date())
  }

  const renderDayView = () => {
    const key = getDayKey(selectedDate)
    const dayEvents = groupedByDay.get(key) || []

    if (!dayEvents.length && !loading) {
      return <p className="mt-4 text-xs text-muted-foreground">No events for this day.</p>
    }

    return (
      <ul className="divide-y divide-border text-xs">
        {dayEvents.map((ev) => (
          <li key={ev.id}>
            <button
              type="button"
              onClick={() => setSelectedEvent(ev)}
              className={`w-full text-left px-3 py-2 hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                selectedEvent?.id === ev.id ? 'bg-muted/80' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-foreground truncate">{ev.summary || 'Untitled event'}</span>
                <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                  {formatEventTimeRange(ev)}
                </span>
              </div>
              {ev.location && (
                <p className="mt-0.5 text-[10px] text-muted-foreground truncate">{ev.location}</p>
              )}
            </button>
          </li>
        ))}
      </ul>
    )
  }

  const renderWeekView = () => {
    const start = new Date(selectedDate)
    const weekday = start.getDay() === 0 ? 6 : start.getDay() - 1
    start.setDate(start.getDate() - weekday)

    const days: Date[] = []
    for (let i = 0; i < 7; i += 1) {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      days.push(d)
    }

    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 h-full">
        {days.map((day) => {
          const key = getDayKey(day)
          const list = groupedByDay.get(key) || []
          const isToday = key === todayKey
          const isSelectedDay = key === selectedKey
          return (
            <section
              key={key}
              className={`flex flex-col rounded-md border overflow-hidden min-h-[140px] ${
                isToday
                  ? 'border-blue-500 bg-blue-50/70'
                  : isSelectedDay
                    ? 'border-blue-400 bg-blue-50/40'
                    : 'border-border bg-card'
              }`}
            >
              <header className="px-2 py-1 border-b border-border flex items-center justify-between">
                <span
                  className={`text-[11px] font-medium ${
                    isToday ? 'text-blue-700' : 'text-foreground'
                  }`}
                >
                  {day.toLocaleDateString(undefined, { weekday: 'short' })}
                </span>
                <span
                  className={`text-[11px] ${
                    isToday ? 'text-blue-700 font-semibold' : 'text-muted-foreground'
                  }`}
                >
                  {day.getDate()}
                </span>
              </header>
              <div className="flex-1 overflow-auto">
                {!list.length ? (
                  <p className="px-2 py-1 text-[10px] text-muted-foreground">No events</p>
                ) : (
                  <ul className="divide-y divide-border text-[11px]">
                    {list.map((ev) => (
                      <li key={ev.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedEvent(ev)}
                          className={`w-full text-left px-2 py-1 hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                            selectedEvent?.id === ev.id ? 'bg-muted/80' : ''
                          }`}
                        >
                          <div className="flex flex-col gap-0.5">
                            <span className="truncate text-foreground">{ev.summary || 'Untitled'}</span>
                            <span className="text-[10px] text-muted-foreground">{formatEventTimeRange(ev)}</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )
        })}
      </div>
    )
  }

  const renderMonthView = () => {
    const year = selectedDate.getFullYear()
    const month = selectedDate.getMonth()

    const firstOfMonth = new Date(year, month, 1)
    const firstWeekday = firstOfMonth.getDay() === 0 ? 6 : firstOfMonth.getDay() - 1

    const days: Date[] = []
    const start = new Date(firstOfMonth)
    start.setDate(firstOfMonth.getDate() - firstWeekday)

    for (let i = 0; i < 42; i += 1) {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      days.push(d)
    }

    return (
      <div className="flex flex-col gap-3 h-full">
        <div className="grid grid-cols-7 text-[11px] text-muted-foreground px-1">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label) => (
            <div key={label} className="text-center font-medium">
              {label}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 grid-rows-6 gap-[3px] bg-border/60 text-[11px] rounded-md p-[3px] flex-1">
          {days.map((day, idx) => {
            const inMonth = day.getMonth() === month
            const key = getDayKey(day)
            const list = groupedByDay.get(key) || []
            const isToday = key === todayKey
            const isSelectedDay = key === selectedKey

            const weekday = day.getDay()
            const isWeekend = weekday === 0 || weekday === 6

            const sortedEvents = [...list].sort((a, b) => {
              const sa = parseEventDate(a.start)?.getTime() ?? 0
              const sb = parseEventDate(b.start)?.getTime() ?? 0
              return sa - sb
            })

            return (
              <section
                key={`${key}-${idx}`}
                className={`flex flex-col overflow-hidden rounded-md min-h-0 ${
                  !inMonth
                    ? 'bg-transparent border-none pointer-events-none'
                    : isToday
                      ? 'border border-blue-500 bg-blue-50/80'
                      : isSelectedDay
                        ? 'border border-blue-400 bg-blue-50/40'
                        : isWeekend
                          ? 'border bg-muted/60 border-border'
                          : 'border bg-card border-border'
                }`}
              >
                <header className="px-1 py-0.5 flex items-center justify-between">
                  {inMonth ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedDate(day)
                        setView('day')
                      }}
                      className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-medium focus:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                        isToday
                          ? 'bg-blue-600 text-white'
                          : 'text-foreground hover:bg-muted'
                      }`}
                    >
                      {day.getDate()}
                    </button>
                  ) : (
                    <span className="inline-flex h-5 w-5" />
                  )}
                </header>
                <div className="flex-1 overflow-hidden px-1 pb-1 space-y-0.5">
                  {inMonth &&
                    sortedEvents.slice(0, 3).map((ev) => (
                      <button
                        key={ev.id}
                        type="button"
                        onClick={() => setSelectedEvent(ev)}
                        className="block w-full truncate text-left text-[11px] hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      >
                        <span>{ev.summary || 'Untitled'}</span>
                      </button>
                    ))}
                  {inMonth && sortedEvents.length > 3 && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedDate(day)
                        setView('day')
                      }}
                      className="px-1 text-[9px] text-blue-600 hover:underline text-left w-full"
                    >
                      +{sortedEvents.length - 3} more
                    </button>
                  )}
                </div>
              </section>
            )
          })}
        </div>
      </div>
    )
  }

  const renderTimeline = () => {
    if (loading) {
      return (
        <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground">
          Loading events...
        </div>
      )
    }

    if (error) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )
    }

    if (view === 'day') return renderDayView()
    if (view === 'week') return renderWeekView()
    return renderMonthView()
  }

  const viewLabel = (() => {
    if (view === 'day') {
      return selectedDate.toLocaleDateString(undefined, {
        weekday: 'long',
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    }
    if (view === 'week') {
      const start = new Date(selectedDate)
      const weekday = start.getDay() === 0 ? 6 : start.getDay() - 1
      start.setDate(start.getDate() - weekday)
      const end = new Date(start)
      end.setDate(start.getDate() + 6)
      return `${start.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
      })} - ${end.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })}`
    }
    return selectedDate.toLocaleDateString(undefined, {
      month: 'long',
      year: 'numeric',
    })
  })()

  const renderDetailPanel = () => {
    if (!selectedEvent) {
      return (
        <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
          Select an event to see details.
        </div>
      )
    }

    const startLabel = formatEventDateLabel(selectedEvent)
    const timeLabel = formatEventTimeRange(selectedEvent)

    return (
      <div className="h-full overflow-auto p-4 text-xs space-y-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Selected event</p>
          <h2 className="text-sm font-semibold text-foreground break-words">
            {selectedEvent.summary || 'Untitled event'}
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {startLabel}
            {timeLabel && <span className="ml-1">· {timeLabel}</span>}
          </p>
          {selectedEvent.location && (
            <p className="mt-1 text-[11px] text-muted-foreground">Location: {selectedEvent.location}</p>
          )}
          {selectedEvent.hangoutLink && (
            <p className="mt-1 text-[11px] text-primary truncate">
              <a href={selectedEvent.hangoutLink} target="_blank" rel="noreferrer" className="hover:underline">
                Join meeting
              </a>
            </p>
          )}
          {selectedEvent.htmlLink && (
            <p className="mt-1 text-[11px] text-primary truncate">
              <a href={selectedEvent.htmlLink} target="_blank" rel="noreferrer" className="hover:underline">
                Open in Google Calendar
              </a>
            </p>
          )}
        </div>

        {selectedEvent.description && (
          <div>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Description</p>
            <p className="text-xs whitespace-pre-wrap break-words text-foreground">
              {selectedEvent.description}
            </p>
          </div>
        )}

        {selectedEvent.attendees && selectedEvent.attendees.length > 0 && (
          <div>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Attendees</p>
            <ul className="space-y-0.5">
              {selectedEvent.attendees.map((a, idx) => (
                <li key={a.email || a.displayName || idx} className="flex items-center justify-between gap-2">
                  <span className="truncate text-foreground">
                    {a.displayName || a.email || 'Unknown'}
                  </span>
                  {a.responseStatus && (
                    <span className="text-[10px] text-muted-foreground capitalize">
                      {a.responseStatus}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Context & notes</p>
          <p className="text-[11px] text-muted-foreground">
            In future, this panel can show pre-meeting context from Slack, Gmail and Notion,
            and link to a dedicated Notion meeting doc.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full w-full flex flex-col bg-background">
      <header className="shrink-0 border-b border-border px-4 py-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <button
            type="button"
            onClick={handleToday}
            className="rounded-md border border-border bg-card px-2 py-1 text-xs font-medium text-foreground hover:bg-muted"
          >
            Today
          </button>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handlePrev}
              aria-label="Previous period"
              className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground hover:bg-muted"
            >
              {'<'}
            </button>
            <button
              type="button"
              onClick={handleNext}
              aria-label="Next period"
              className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground hover:bg-muted"
            >
              {'>'}
            </button>
          </div>
          <p
            className="text-xs font-medium text-foreground truncate max-w-[180px] sm:max-w-xs md:max-w-md"
            title={viewLabel}
          >
            {viewLabel}
          </p>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={() => setView('day')}
            className={`px-2 py-1 rounded-md border text-xs font-medium ${
              view === 'day'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-card text-foreground border-border hover:bg-muted'
            }`}
          >
            Today
          </button>
          <button
            type="button"
            onClick={() => setView('week')}
            className={`px-2 py-1 rounded-md border text-xs font-medium ${
              view === 'week'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-card text-foreground border-border hover:bg-muted'
            }`}
          >
            This week
          </button>
          <button
            type="button"
            onClick={() => setView('month')}
            className={`px-2 py-1 rounded-md border text-xs font-medium ${
              view === 'month'
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-card text-foreground border-border hover:bg-muted'
            }`}
          >
            This month
          </button>
        </div>
      </header>

      <main className="flex-1 flex flex-col md:flex-row overflow-hidden">
        <section className="flex-1 min-h-0 border-b md:border-b-0 md:border-r border-border">
          <div className="h-full w-full overflow-auto p-3 text-xs">{renderTimeline()}</div>
        </section>
        <aside className="w-full md:w-80 lg:w-96 shrink-0 h-56 md:h-full border-t md:border-t-0 md:border-l border-border bg-card">
          {renderDetailPanel()}
        </aside>
      </main>
    </div>
  )
}
