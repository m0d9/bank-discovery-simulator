export interface ChatMessage {
  n: number;
  role: 'student' | 'client';
  text: string;
}

interface ChatLogProps {
  /** In order; the opening line comes first. */
  messages: ChatMessage[];
  /** What a screen reader hears before each message, e.g. "You said:". */
  speakerLabel: (role: ChatMessage['role']) => string;
  /** A live log announces each new message once. A transcript kept for reference isn't live. */
  live?: boolean;
  /** The id of the element that names the live log. */
  labelledBy?: string;
}

/** The conversation. Each message keeps its turn number as its key, so a message is never
 * re-created (and never re-announced) as the conversation grows. */
export function ChatLog({ messages, speakerLabel, live = true, labelledBy }: ChatLogProps) {
  const list = (
    <ol className="flex flex-col gap-3">
      {messages.map((message) => (
        <MessageBubble key={message.n} message={message} speaker={speakerLabel(message.role)} />
      ))}
    </ol>
  );
  if (!live) return list;
  return (
    <div role="log" aria-live="polite" aria-relevant="additions" aria-labelledby={labelledBy}>
      {list}
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
  speaker: string;
}

/** One message. The student's sit at the inline end and the client's at the start, so the
 * layout mirrors in Arabic; `dir="auto"` lets each message keep its own direction. The id lets
 * a link move focus to a turn. */
export function MessageBubble({ message, speaker }: MessageBubbleProps) {
  const fromStudent = message.role === 'student';
  return (
    <li
      id={`turn-${String(message.n)}`}
      tabIndex={-1}
      className={`max-w-[85%] rounded-xl px-4 py-3 ${
        fromStudent
          ? 'self-end rounded-ee-sm bg-brand-tint'
          : 'self-start rounded-es-sm border border-line bg-surface'
      }`}
    >
      <span className="sr-only">{speaker}</span>
      <p dir="auto" className="text-start whitespace-pre-wrap wrap-break-word text-ink">
        {message.text}
      </p>
    </li>
  );
}
