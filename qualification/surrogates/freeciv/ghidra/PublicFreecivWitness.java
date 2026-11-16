// Public-source Ghidra headless witness. No private binary bytes or addresses exported.
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

public class PublicFreecivWitness extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2 || !args[0].matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("GHIDRA_WITNESS_ARGUMENTS_INVALID");
        }
        if (currentProgram == null) {
            throw new IllegalStateException("GHIDRA_PROGRAM_NOT_LOADED");
        }
        String imageHash = currentProgram.getExecutableSHA256();
        if (imageHash == null || !args[0].equals(imageHash.toLowerCase(Locale.ROOT))) {
            throw new IllegalStateException("GHIDRA_IMPORTED_ARTIFACT_DIGEST_MISMATCH");
        }
        long functionCount = 0L;
        long intervalCount = 0L;
        FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(true);
        while (iterator.hasNext()) {
            Function function = iterator.next();
            functionCount++;
            AddressRangeIterator ranges = function.getBody().getAddressRanges();
            long bodyRanges = 0L;
            while (ranges.hasNext()) {
                AddressRange range = ranges.next();
                if (range.getMinAddress().compareTo(range.getMaxAddress()) > 0) {
                    throw new IllegalStateException("GHIDRA_INVALID_FUNCTION_INTERVAL");
                }
                bodyRanges++;
                intervalCount++;
            }
            if (bodyRanges == 0L) {
                throw new IllegalStateException("GHIDRA_EMPTY_FUNCTION_BODY");
            }
        }
        if (functionCount < 100L || intervalCount < functionCount) {
            throw new IllegalStateException("GHIDRA_FUNCTION_DISCOVERY_INSUFFICIENT");
        }
        Path output = Paths.get(args[1]).toAbsolutePath();
        Files.createDirectories(output.getParent());
        String json = "{\"schema\":\"freeciv-ghidra-static/v0.1\","
                + "\"execution_class\":\"REAL_GHIDRA_SOURCE_KNOWN_STATIC_ONLY\","
                + "\"artifact_sha256\":\"" + imageHash.toLowerCase(Locale.ROOT) + "\","
                + "\"function_count\":" + functionCount + ","
                + "\"interval_count\":" + intervalCount + ","
                + "\"pc_correlated\":false}";
        Files.write(output, json.getBytes(StandardCharsets.UTF_8));
        println("PUBLIC_GHIDRA_STATIC_WITNESS_COMPLETE");
    }
}
