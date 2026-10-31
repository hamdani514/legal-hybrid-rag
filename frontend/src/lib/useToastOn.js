import { useEffect } from 'react';
import { toast } from './toast';

/**
 * Show a toast whenever a component's message state gets a new value.
 *
 *   const [errorMsg, setErrorMsg] = useState('');
 *   useToastOn(errorMsg, 'error');
 *
 * Every branch that already sets the message — validation, server refusals,
 * network failures — then also raises the top-right toast, with no change to
 * the branches themselves. Empty values (the reset at the start of a submit)
 * show nothing.
 *
 * For state set by a list that refreshes on a timer, pass { dedupeMs } so a
 * lasting failure is announced once rather than on every refresh.
 */
export default function useToastOn(message, type = 'error', { dedupeMs } = {}) {
  useEffect(() => {
    if (typeof message === 'string' && message.trim()) {
      toast[type](message, dedupeMs ? { dedupeMs } : undefined);
    }
  }, [message, type, dedupeMs]);
}
