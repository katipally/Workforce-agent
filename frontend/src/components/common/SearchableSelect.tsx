import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'

export type SearchableSelectOption = {
  value: string
  label: string
  disabled?: boolean
}

type Props = {
  id?: string
  value: string
  onChange: (value: string) => void
  options: SearchableSelectOption[]
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  disabled?: boolean

  allowClear?: boolean
  clearLabel?: string

  containerClassName?: string
  triggerClassName?: string
  dropdownClassName?: string
  optionClassName?: string

  fullWidth?: boolean
}

export function SearchableSelect({
  id,
  value,
  onChange,
  options,
  placeholder = 'Select…',
  searchPlaceholder = 'Search…',
  emptyText = 'No results.',
  disabled = false,

  allowClear = false,
  clearLabel = 'Clear selection',
  containerClassName,
  triggerClassName,
  dropdownClassName,
  optionClassName,
  fullWidth = false,
}: Props) {
  const [open, setOpen] = useState(false)

  const selected = useMemo(() => options.find((o) => o.value === value) || null, [options, value])

  const commit = (nextValue: string) => {
    onChange(nextValue)
    setOpen(false)
  }

  return (
    <div className={cn(fullWidth && 'w-full', containerClassName)}>
      <Popover
        open={open}
        onOpenChange={(next: boolean) => {
          if (disabled) return
          setOpen(next)
        }}
      >
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn('justify-between', fullWidth && 'w-full', triggerClassName)}
          >
            <span className={cn('truncate', !selected && 'text-muted-foreground')}>
              {selected?.label || placeholder}
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-70" />
          </Button>
        </PopoverTrigger>

        <PopoverContent
          align="start"
          className={cn(
            'p-0',
            fullWidth && 'w-[--radix-popover-trigger-width]',
            dropdownClassName,
          )}
        >
          <Command>
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              <CommandEmpty>{emptyText}</CommandEmpty>
              <CommandGroup>
                {allowClear && (
                  <CommandItem
                    value={clearLabel}
                    onSelect={() => commit('')}
                    className={cn('text-muted-foreground', optionClassName)}
                  >
                    {clearLabel}
                  </CommandItem>
                )}

                {options.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={opt.label}
                    disabled={opt.disabled}
                    onSelect={() => {
                      if (opt.disabled) return
                      commit(opt.value)
                    }}
                    className={cn(optionClassName)}
                  >
                    <Check
                      className={cn(
                        'mr-2 h-4 w-4',
                        opt.value === value ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    <span className="truncate">{opt.label}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}
