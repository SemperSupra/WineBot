// SPDX-License-Identifier: MIT
// Synthetic ETW user provider, ETL collection and TraceEvent decoding.
// No third-party target, kernel providers, or raw trace publication.
using System;
using System.Diagnostics.Tracing;
using System.IO;
using System.Threading;
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

    // A correct count alone can hide duplicate/missing or reordered states.
    private static bool ExactlyOrdered(IReadOnlyList<int> states)
    {
        if (states.Count != Expected) return false;
        for (int i = 0; i < Expected; i++)
            if (states[i] != i + 1) return false;
        return true;
    }

    private static int SelfTest()
    {
        if (!ExactlyOrdered(new[] { 1, 2, 3 }) ||
            ExactlyOrdered(new[] { 1, 1, 3 }) ||
            ExactlyOrdered(new[] { 1, 3, 2 }) ||
            ExactlyOrdered(new[] { 1, 2 }) ||
            ExactlyOrdered(new[] { 1, 2, 3, 3 }) ||
            ExactlyOrdered(Array.Empty<int>())) return 11;
        Console.WriteLine("PASS: etw_sequence_negative_controls");
        return 0;
    }

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test") return SelfTest();
        if (args.Length != 0 || !OperatingSystem.IsWindows()) return 2;
        var file = Path.Combine(Path.GetTempPath(),
            "winebot-etw-" + Guid.NewGuid().ToString("N") + ".etl");
        var sessionName = "WineBotRDTE-" + Guid.NewGuid().ToString("N");
        var providerGuid = EventSource.GetGuid(typeof(SyntheticTransitionEvents));

        try
        {
            // No shared ETW session and no kernel provider. Dispose/stop prior
            // to decoding; an ETL file has a finite, reproducible end of stream.
            using (var emitter = new SyntheticTransitionEvents())
            using (var session = new TraceEventSession(sessionName, file))
            {
                session.StopOnDispose = true;
                session.EnableProvider(providerGuid);
                Thread.Sleep(500);
                for (int i = 1; i <= Expected; i++)
                {
                    emitter.Transition(i);
                    Thread.Sleep(100);
                }
                Thread.Sleep(1000); // bounded ETW buffer flush allowance
            }

            int count = 0;
            int unexpected = 0;
            int matchingProvider = 0;
            int matchingProcess = 0;
            var seenStates = new System.Collections.Generic.List<int>();
            using (var source = new ETWTraceEventSource(file))
            {
                source.Dynamic.All += ev =>
                {
                    if (ev.ProviderGuid != providerGuid) return;
                    matchingProvider++;
                    if (ev.ProcessID != Environment.ProcessId) return;
                    matchingProcess++;
                    // Exclude EventSource manifests and other provider metadata.
                    if ((int)ev.ID != 1) return;
                    try
                    {
                        int state = Convert.ToInt32(ev.PayloadByName("state"));
                        if (state < 1 || state > Expected)
                            Interlocked.Increment(ref unexpected);
                        seenStates.Add(state);
                        Interlocked.Increment(ref count);
                    }
                    catch
                    {
                        Interlocked.Increment(ref unexpected);
                    }
                };
                source.Process(); // finite file, never a live infinite reader
            }

            // Fixed classification only; no event content in public logs.
            if (matchingProvider == 0) { Console.Error.WriteLine("ETW_FAIL_NO_PROVIDER"); return 4; }
            if (matchingProcess == 0) { Console.Error.WriteLine("ETW_FAIL_NO_MATCHING_PROCESS"); return 5; }
            if (count < Expected) { Console.Error.WriteLine(unexpected > 0 ? "ETW_FAIL_DECODE" : "ETW_FAIL_MISSING_EVENTS"); return 6; }
            if (count > Expected) { Console.Error.WriteLine("ETW_FAIL_EXTRA_EVENTS"); return 8; }
            if (unexpected != 0) { Console.Error.WriteLine("ETW_FAIL_PAYLOAD"); return 7; }
            if (!ExactlyOrdered(seenStates)) { Console.Error.WriteLine("ETW_FAIL_SEQUENCE"); return 9; }
            Console.WriteLine("PASS: native_etw_file_capture_decode");
            return 0;
        }
        finally
        {
            // No raw ETW buffers leave the disposable runner.
            if (File.Exists(file)) File.Delete(file);
        }
    }
}
