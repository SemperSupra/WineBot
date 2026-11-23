// SPDX-License-Identifier: MIT
// Synthetic user-mode ETW producer and TraceEvent consumer. No target data.
using System;
using System.Diagnostics.Tracing;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Session;

[EventSource(Name = "WineBotRDTE-SyntheticTransition")]
sealed class SyntheticTransitionEvents : EventSource
{
    [Event(1, Level = EventLevel.Informational)]
    public void Transition(int state) => WriteEvent(1, state);
}

static class Program
{
    private const int Expected = 3;

    private static int Main()
    {
        if (!OperatingSystem.IsWindows()) return 2;
        // Unique per disposable run, never reusing or stopping another session.
        var sessionName = "WineBotRDTE-" + Guid.NewGuid().ToString("N");
        var providerGuid = EventSource.GetGuid(typeof(SyntheticTransitionEvents));
        using var emitter = new SyntheticTransitionEvents();
        using var session = new TraceEventSession(sessionName);
        session.StopOnDispose = true;

        int count = 0;
        int unexpected = 0;
        session.Source.Dynamic.All += ev =>
        {
            if (ev.ProviderGuid != providerGuid || ev.ProcessID != Environment.ProcessId) return;
            try
            {
                var state = Convert.ToInt32(ev.PayloadByName("state"));
                if (state < 1 || state > Expected) Interlocked.Increment(ref unexpected);
                Interlocked.Increment(ref count);
            }
            catch
            {
                Interlocked.Increment(ref unexpected);
            }
        };
        session.EnableProvider(providerGuid);
        var reader = Task.Run(() => session.Source.Process());

        // Allow live listener startup. This is fixture synchronization, not a
        // claim that ETW gives perfect event completeness or total ordering.
        Thread.Sleep(500);
        for (int i = 1; i <= Expected; i++)
        {
            emitter.Transition(i);
            Thread.Sleep(100);
        }

        var cutoff = DateTime.UtcNow.AddSeconds(12);
        while (Volatile.Read(ref count) < Expected && DateTime.UtcNow < cutoff)
            Thread.Sleep(50);
        session.Source.StopProcessing();
        if (!reader.Wait(TimeSpan.FromSeconds(8))) return 3;
        if (Volatile.Read(ref count) != Expected || Volatile.Read(ref unexpected) != 0)
            return 4;

        // Only fixed markers: no provider payloads, session IDs or raw trace.
        Console.WriteLine("PASS: native_etw_source_capture_and_decode");
        return 0;
    }
}
