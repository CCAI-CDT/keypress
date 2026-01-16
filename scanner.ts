// npx --package=typescript -- tsc -t ES6 scanner.ts

export interface ScannerInputCallback {
  (result: string, category: ScannerEventCategories): unknown
}

export type ScannerCardCategories =
  | 'card'
  | 'barcode'
  | 'library'
  | 'numeric'
  | 'unknown'

export type ScannerEventCategories = ScannerCardCategories | 'key'

export interface ScannerOptions {
  timeoutMs: number
  duplicateRemovalMs: number
  numpadAlwaysDigits: boolean
  allowBackspace: boolean
  allowPaste: boolean
  inputOnTimeout: boolean
  ignoreKeys: string[]
  eventKeys: string[]
  categoryMatchers: Record<ScannerCardCategories, Function[]>
  verboseLog: boolean
}

// Receiver for keyboard-emulating barcode and card scanners.
// User-supplied callback fired when keystrokes entered and Enter pressed within a timeout period (2 seconds):
// * `input` set to the string of keys entered.
// * `category` set to the recognised type of scan (`'card', 'barcode', 'library'`),
//   `'numeric'` if another number, `'unknown'` otherwise.
export class Scanner {
  inputReceivedCallback: ScannerInputCallback
  buffer: string
  timerId: number | null
  options: ScannerOptions
  lastScanTime: number | null
  lastScanId: string | null

  constructor(callback: ScannerInputCallback, options?: ScannerOptions) {
    this.inputReceivedCallback = callback

    // Configuration
    this.options = Object.assign(
      {
        timeoutMs: 2 * 1000,
        duplicateRemovalMs: 1 * 1000,
        numpadAlwaysDigits: true,
        allowBackspace: true,
        allowPaste: true,
        inputOnTimeout: true,
        ignoreKeys: [],
        eventKeys: ['/', '*', '-', '+', '=', '^', '.'],
        categoryMatchers: {
          card: [Scanner.matchRfidCard],
          barcode: [Scanner.matchGtinBarcode, Scanner.matchAmazonBarcode],
          library: [Scanner.matchLibraryBarcode],
          numeric: [Scanner.matchNumeric],
          unknown: [Scanner.matchAnything],
        },
        verboseLog: false,
      },
      options ?? {}
    )

    // State
    this.buffer = ''
    this.timerId = null
    this.lastScanTime = null
    this.lastScanId = null

    // Bind event handlers
    this.timedOut = this.timedOut.bind(this)
    this.keyDown = this.keyDown.bind(this)
    this.paste = this.paste.bind(this)

    // this.timedOutBound = this.timedOut.bind(this)
    // this.keyDownBound = this.keyDown.bind(this)

    document.addEventListener('keydown', this.keyDown)

    if (this.options.allowPaste) {
      document.addEventListener('paste', this.paste)
    }
  }

  destroy() {
    document.removeEventListener('keydown', this.keyDown)
    document.removeEventListener('paste', this.paste)
    if (this.timerId !== null) {
      window.clearTimeout(this.timerId)
      this.timerId = null
    }
  }

  // Returns the input string as a normalized RFID card id, null otherwise
  static matchRfidCard(input: string) {
    if (!input) return null
    // All 10 characters must be digits
    if (!/^\d{10}$/.test(input)) return null
    // As a decimal value, must be within the unsigned 32-bit integer range
    const value = parseInt(input, 10)
    if (value > 0xffffffff) return null
    return input
  }

  // Returns the input string as a normalized GTIN (EAN-13/8, UPC-A) barcode, null otherwise
  // (works with ISBN-13, but not ISBN-10, as this would clash with the RFID IDs)
  static matchGtinBarcode(input: string) {
    if (!input) return null
    // All 8 (EAN-8), 12 (UPC-A), 13 (EAN-13) characters must be digits
    if (![8, 12, 13].includes(input.length) || !/^\d*$/.test(input)) return null
    // Sum from right, even (weighted 1) and odd digits (weighted 3), excluding check digit
    let sum = 0
    for (let i = input.length - 1 - 1; i >= 0; i--) {
      sum += ((input.length - 1 + i) % 2 ? 3 : 1) * parseInt(input[i], 10)
    }
    // Verify check digit
    const calculatedCheckDigit = (10 - (sum % 10)) % 10
    const suppliedCheckDigit = parseInt(input[input.length - 1])
    if (calculatedCheckDigit != suppliedCheckDigit) return null
    return input
  }

  // Returns the matching Amazon FNSKU (Fulfilment Network Stock Keeping Unit), or
  // ASIN (Amazon Standard Identification Number) excluding books (ISBN-10, as this
  // would clash with the RFID IDs), null otherwise
  static matchAmazonBarcode(input: string) {
    if (!input) return null
    // Initial character must be 'X' (FNSKU), or 'B' (ASIN), and remaining 9 characters must be alphanumeric.
    if (!/^[BbXx][A-Za-z0-9]{9}$/.test(input)) return null
    return input.toUpperCase()
  }

  // Returns input string as a normalized library barcode on staff/student cards, null otherwise
  static matchLibraryBarcode(input: string) {
    if (!input) return null
    // Must match library ID format: "U00000000" (note: last digit may be 'X' if check digit value is 10)
    if (!/^[Uu]\d{7}[Xx0-9]$/.test(input)) return null
    const digits = input.slice(1)
    // These weights were found by exhaustive search, and appear to match the last seven
    // used in Australian TFNs (Tax File Numbers), omitting the initial two.
    const weights = [1, 4, 3, 7, 5, 8, 6, 9, 10] // first two weights are not used
    // Sum weighted digits, excluding check digit
    let sum = 0
    for (let i = 0; i < digits.length - 1; i++) {
      sum +=
        weights[weights.length - (digits.length - 1) + i] * parseInt(digits[i])
    }
    // Verify check digit
    const calculatedCheckValue = (11 - (sum % 11)) % 11
    const suppliedCheckDigit = digits[digits.length - 1]
    const suppliedCheckValue =
      suppliedCheckDigit == 'X' || suppliedCheckDigit == 'x'
        ? 10
        : parseInt(suppliedCheckDigit, 10)
    if (calculatedCheckValue != suppliedCheckValue) return null
    return input.toUpperCase()
  }

  // Returns non-empty numeric input string, null otherwise
  static matchNumeric(input: string) {
    if (!input) return null
    if (!/^\d+$/.test(input)) return null
    return input
  }

  // Returns non-empty input string, null otherwise
  static matchAnything(input: string) {
    if (!input) return null
    return input
  }

  // Handles entered string, returns true if handled
  inputReceived(input: string) {
    // Determine if this is a duplicate scan, and how long ago it is from
    const now = Date.now()
    let duplicateAgeMs: number | null = null
    if (
      this.lastScanTime !== null &&
      this.lastScanId !== null &&
      input === this.lastScanId
    ) {
      duplicateAgeMs = now - this.lastScanTime
    }

    // Track the current scan for future duplicate detection
    this.lastScanTime = now
    this.lastScanId = input

    // Recent duplicates are ignored
    if (
      duplicateAgeMs !== null &&
      duplicateAgeMs < this.options.duplicateRemovalMs
    ) {
      return false
    }

    for (const [category, matcherList] of Object.entries(
      this.options.categoryMatchers
    )) {
      for (const matcher of matcherList) {
        const result = matcher(input)
        if (result !== null) {
          // Unless explicitly marked as unhandled in callback, return true (otherwise try next matcher)
          if (
            this.inputReceivedCallback(
              result,
              category as ScannerCardCategories
            ) !== false
          ) {
            return true
          }
        }
      }
    }
    return false
  }

  // Handles 'keydown' events on the page.
  // Minimizes interfering with with standard page navigation keys unless characters are typed.
  // The input buffer is reset unless Enter is pressed within the timeout period.
  keyDown(event: KeyboardEvent) {
    // Verbose debug key logging
    if (this.options.verboseLog) {
      console.log(
        `KEY: @${new Date()
          .toISOString()
          .replace('T', ' ')
          .replace('Z', '')} #${event.keyCode} (${event.altKey}/${
          event.ctrlKey
        }/${event.metaKey}/${event.shiftKey}) =${event.key}`
      )
    }

    if (this.timerId !== null) {
      clearTimeout(this.timerId)
      this.timerId = null
    }
    let key = event.key

    // Map the numeric keypad to numbers even when Num Lock is not pressed
    if (
      this.options.numpadAlwaysDigits &&
      event.location == KeyboardEvent.DOM_KEY_LOCATION_NUMPAD
    ) {
      const numPadMap: Record<number, string | undefined> = {
        0x2d: '0', // Insert
        0x23: '1', // End
        0x28: '2', // ArrowDown
        0x22: '3', // PageDown
        0x25: '4', // ArrowLeft
        0x0c: '5', // Clear
        0x27: '6', // ArrowRight
        0x24: '7', // Home
        0x26: '8', // ArrowUp
        0x21: '9', // PageUp
        0x2e: '.', // Delete
      }
      if (event.keyCode in numPadMap) {
        key = numPadMap[event.keyCode]!
      }
    }

    const modifier = event.altKey || event.ctrlKey || event.metaKey // event.shiftKey

    if (modifier || this.options.ignoreKeys.includes(key)) {
      // Ignored key (e.g. one handled elsewhere in the application)
    } else if (this.options.eventKeys.includes(key)) {
      // Event key
      event.preventDefault()
      this.inputReceivedCallback(key, 'key')
    } else if (this.buffer != '' && event.keyCode == 13) {
      // Enter
      event.preventDefault()
      this.inputReceived(this.buffer)
      this.buffer = ''
    } else if (
      this.options.allowBackspace &&
      this.buffer != '' &&
      event.keyCode == 8
    ) {
      // Backspace
      event.preventDefault()
      this.buffer = this.buffer.slice(0, -1)
    } else if (
      key &&
      key.length == 1 &&
      !(this.buffer == '' && event.keyCode == 32) &&
      event.keyCode != 13
    ) {
      // Character keys
      event.preventDefault()
      this.buffer += key
      this.timerId = window.setTimeout(this.timedOut, this.options.timeoutMs)
    }
  }

  timedOut() {
    if (this.options.inputOnTimeout) {
      this.inputReceived(this.buffer)
    }
    this.buffer = ''
    this.timerId = null
  }

  paste(event: ClipboardEvent) {
    let text = event.clipboardData?.getData('text')
    if (!text) return

    // Ignore trailing CR/LF
    if (text.length > 0 && text[text.length - 1] == '\n')
      text = text.slice(0, -1)
    if (text.length > 0 && text[text.length - 1] == '\r')
      text = text.slice(0, -1)
    // Check remaining number of new lines
    const newLines = [...text].reduce(
      (sum, char) => sum + (char == '\n' ? 1 : 0),
      0
    )
    // Only process a single line
    if (newLines == 0) {
      // Consume paste event if handled, and reset any input state
      if (this.inputReceived(text)) {
        event.preventDefault()
        if (this.timerId !== null) {
          clearTimeout(this.timerId)
          this.timerId = null
        }
        this.buffer = ''
      }
    }
  }
}
