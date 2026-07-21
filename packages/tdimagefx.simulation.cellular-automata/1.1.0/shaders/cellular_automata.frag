// Private Life-like state: R = alive, G = neighbour density, B/A = state marker.
// Input 0 is source; input 1 is the previous private state.
uniform float uBirth;
uniform float uSurvival;
uniform float uSeed;

layout(location = 0) out vec4 fragColor;

float stateIsEncoded(vec4 state) {
    return step(0.99, state.b) * (1.0 - step(0.01, state.a));
}

float sourceSeed(vec2 uv) {
    vec3 source = texture(sTD2DInputs[0], uv).rgb;
    float luma = dot(source, vec3(0.2126, 0.7152, 0.0722));
    return step(1.0 - clamp(uSeed, 0.0, 1.0), luma);
}

void main() {
    vec2 uv = vUV.st;
    vec2 px = 1.0 / vec2(textureSize(sTD2DInputs[1], 0));
    vec4 prior = texture(sTD2DInputs[1], uv);

    if (stateIsEncoded(prior) < 0.5) {
        float initialCell = sourceSeed(uv);
        fragColor = TDOutputSwizzle(vec4(initialCell, 0.0, 1.0, 0.0));
        return;
    }

    float center = step(0.5, prior.r);
    float neighbors = 0.0;
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            if (x != 0 || y != 0) {
                neighbors += step(0.5, texture(sTD2DInputs[1], uv + vec2(x, y) * px).r);
            }
        }
    }

    float birthCount = floor(clamp(uBirth, 1.0, 8.0) + 0.5);
    float survivalCount = floor(clamp(uSurvival, 1.0, 8.0) + 0.5);
    float born = 1.0 - step(0.5, abs(neighbors - birthCount));
    float survives = 1.0 - step(0.5, abs(neighbors - survivalCount));
    float nextCell = mix(born, survives, center);
    fragColor = TDOutputSwizzle(vec4(nextCell, neighbors / 8.0, 1.0, 0.0));
}
