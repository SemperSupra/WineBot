// Ephemeral function-body interval export for public source-known Freeciv only.
// @category Freeciv.Surrogate
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressRangeIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;

public class PublicFreecivPcIntervals extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2 || !args[0].matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("GHIDRA_PC_ARGS_INVALID");
        }
        if (currentProgram == null) {
            throw new IllegalStateException("GHIDRA_PC_NO_PROGRAM");
        }
        String actual = currentProgram.getExecutableSHA256();
        if (actual == null || !actual.toLowerCase(Locale.ROOT).equals(args[0])) {
            throw new IllegalStateException("GHIDRA_PC_DIGEST_MISMATCH");
        }
        long imageBase = currentProgram.getImageBase().getOffset();
        if (imageBase < 0) {
            throw new IllegalStateException("GHIDRA_PC_IMAGE_BASE_INVALID");
        }
        long count = 0;
        long intervalCount = 0;
        StringBuilder data = new StringBuilder(720000);
        data.append("{\"schema\":\"freeciv-ghidra-pc-intervals/v0.1\",\"artifact_sha256\":\"")
            .append(actual.toLowerCase(Locale.ROOT))
            .append("\",\"image_base\":").append(imageBase)
            .append(",\"intervals\":[");
        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        while (functions.hasNext()) {
            Function function = functions.next();
            count++;
            if (count > 200000) throw new IllegalStateException("GHIDRA_PC_FUNCTION_BUDGET");
            AddressRangeIterator ranges = function.getBody().getAddressRanges();
            boolean hasBody = false;
            while (ranges.hasNext()) {
                AddressRange range = ranges.next();
                long start = Math.subtractExact(range.getMinAddress().getOffset(), imageBase);
                long end = Math.addExact(Math.subtractExact(range.getMaxAddress().getOffset(), imageBase), 1);
                if (start < 0 || end <= start) throw new IllegalStateException("GHIDRA_PC_RANGE_INVALID");
                if (intervalCount != 0) data.append(',');
                // Include a function ordinal, not a name, to preserve ambiguous interval provenance.
                data.append('[').append(start).append(',').append(end).append(',').append(count).append(']');
                intervalCount++;
                if (intervalCount > 2000000 || data.length() > 48000000)
                    throw new IllegalStateException("GHIDRA_PC_INTERVAL_BUDGET");
                hasBody = true;
            }
            if (!hasBody) throw new IllegalStateException("GHIDRA_PC_EMPTY_BODY");
        }
        if (count < 100 || intervalCount < count) {
            throw new IllegalStateException("GHIDRA_PC_DISCOVERY_TOO_SMALL");
        }
        data.append("],\"function_count\":").append(count).append('}');
        Path dest = Paths.get(args[1]).toAbsolutePath();
        Files.createDirectories(dest.getParent());
        Files.write(dest, data.toString().getBytes(StandardCharsets.UTF_8));
        println("EPHEMERAL_GHIDRA_PC_INTERVAL_EXPORT_COMPLETE");
    }
}
