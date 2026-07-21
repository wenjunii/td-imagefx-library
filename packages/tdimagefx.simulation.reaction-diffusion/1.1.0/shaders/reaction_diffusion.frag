// Private Gray-Scott state: R = chemical A, G = chemical B, B/A = marker.
// Input 0 is source; input 1 is the previous private state.
uniform float uFeed;
uniform float uKill;
uniform float uDiffusion;
uniform float uSeed;

layout(location = 0) out vec4 fragColor;

float stateIsEncoded(vec4 state) {
    return step(0.99, state.b) * (1.0 - step(0.01, state.a));
}

vec2 chemicalState(vec2 uv) {
    return texture(sTD2DInputs[1], uv).rg;
}

void main() {
    vec2 uv = vUV.st;
    vec2 px = 1.0 / vec2(textureSize(sTD2DInputs[1], 0));
    vec4 prior = texture(sTD2DInputs[1], uv);

    if (stateIsEncoded(prior) < 0.5) {
        vec3 source = texture(sTD2DInputs[0], uv).rgb;
        float initialB = clamp(dot(source, vec3(0.2126, 0.7152, 0.0722)) * uSeed, 0.0, 1.0);
        fragColor = TDOutputSwizzle(vec4(1.0 - initialB, initialB, 1.0, 0.0));
        return;
    }

    vec2 center = prior.rg;
    vec2 laplacian = -center;
    laplacian += 0.20 * (
        chemicalState(uv + vec2(px.x, 0.0)) +
        chemicalState(uv - vec2(px.x, 0.0)) +
        chemicalState(uv + vec2(0.0, px.y)) +
        chemicalState(uv - vec2(0.0, px.y))
    );
    laplacian += 0.05 * (
        chemicalState(uv + px) +
        chemicalState(uv - px) +
        chemicalState(uv + vec2(px.x, -px.y)) +
        chemicalState(uv + vec2(-px.x, px.y))
    );

    float a = center.r;
    float b = center.g;
    float reaction = a * b * b;
    float diffusionA = clamp(uDiffusion, 0.0, 1.5);
    float diffusionB = diffusionA * 0.5;
    float nextA = a + diffusionA * laplacian.r - reaction + uFeed * (1.0 - a);
    float nextB = b + diffusionB * laplacian.g + reaction - (uKill + uFeed) * b;
    fragColor = TDOutputSwizzle(vec4(clamp(nextA, 0.0, 1.0), clamp(nextB, 0.0, 1.0), 1.0, 0.0));
}
